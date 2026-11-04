#!/usr/bin/env python3
"""Build the independent arm64 helpers using an existing iPhoneOS toolchain."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.8.0"


def run(args, seconds=120):
    process = subprocess.Popen([str(arg) for arg in args], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, err = process.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise RuntimeError("native build step timed out")
    if process.returncode:
        raise RuntimeError("%s failed: %s" % (args[0], err[-6000:]))
    return {"tool": Path(str(args[0])).name, "exit": process.returncode,
            "stdout": out[-2000:], "stderr": err[-4000:]}


def digest(file):
    return hashlib.sha256(Path(file).read_bytes()).hexdigest()


def build_activities(sdk, tools, build, stage, steps):
    source = ROOT / "native/activities"
    binary = stage / "icb-activities"
    steps.append(run([tools["clang"], "-target", "arm64-apple-ios16.1", "-isysroot", sdk,
                      "-fobjc-arc", "-fblocks", "-O2", "-Wall", "-Wextra", "-c",
                      source / "ActivityBridge.m", "-o", stage / "ActivityBridge.o"]))
    steps.append(run([tools["swiftc"], "-sdk", sdk, "-target", "arm64-apple-ios16.1",
                      "-swift-version", "5", "-Onone", "-module-cache-path", build / "ModuleCache",
                      "-import-objc-header", source / "ActivityBridge.h", source / "main.swift",
                      stage / "ActivityBridge.o", stage / "libclang_rt.ios.a", "-o", binary]))
    steps.append(run([tools["ldid"], "-S" + str(source / "entitlements.plist"), binary], 10))
    binary.chmod(0o755)
    return binary


def build_browser(sdk, tools, build, stage, steps):
    source = ROOT / "native/browser"
    binary = stage / "icb-open-url"
    steps.append(run([tools["clang"], "-target", "arm64-apple-ios16.1", "-isysroot", sdk,
                      "-fobjc-arc", "-fblocks", "-O2", "-Wall", "-Wextra", "-c",
                      source / "open_url.m", "-o", stage / "open_url.o"]))
    steps.append(run([tools["clang"], "-target", "arm64-apple-ios16.1", "-isysroot", sdk,
                      stage / "open_url.o", "-framework", "Foundation", "-framework", "UIKit",
                      "-o", binary]))
    steps.append(run([tools["ldid"], "-S" + str(source / "entitlements.plist"), binary], 10))
    binary.chmod(0o755)
    return binary


def build_alarms(sdk, tools, build, stage, steps):
    source = ROOT / "native/alarms"
    binary = stage / "icb-alarms"
    steps.append(run([tools["clang"], "-target", "arm64-apple-ios16.1", "-isysroot", sdk,
                      "-fno-objc-arc", "-O2", "-Wall", "-Wextra", "-c",
                      source / "AlarmsBridge.m", "-o", stage / "AlarmsBridge.o"]))
    steps.append(run([tools["clang"], "-target", "arm64-apple-ios16.1", "-isysroot", sdk,
                      stage / "AlarmsBridge.o", "-framework", "Foundation", "-o", binary]))
    steps.append(run([tools["ldid"], "-S" + str(source / "entitlements.plist"), binary], 10))
    binary.chmod(0o755)
    return binary


def build_settings(sdk, tools, build, stage, steps):
    source = ROOT / "native/settings"
    binary = stage / "icb-settings"
    steps.append(run([tools["clang"], "-target", "arm64-apple-ios16.1", "-isysroot", sdk,
                      "-fobjc-arc", "-fblocks", "-O2", "-Wall", "-Wextra", "-c",
                      source / "settings.m", "-o", stage / "settings.o"]))
    steps.append(run([tools["clang"], "-target", "arm64-apple-ios16.1", "-isysroot", sdk,
                      stage / "settings.o", "-framework", "Foundation", "-framework", "UIKit",
                      "-framework", "AVFoundation", "-o", binary]))
    steps.append(run([tools["ldid"], "-S" + str(source / "entitlements.plist"), binary], 10))
    binary.chmod(0o755)
    return binary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk", default=os.environ.get("ICB_SDK"))
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise RuntimeError("build requires an existing Apple-platform toolchain")
    sdk = Path(args.sdk or "/var/jb/opt/sdks/iPhoneOS16.5.sdk").expanduser()
    if not sdk.is_dir():
        raise RuntimeError("set ICB_SDK or --sdk to an installed iPhoneOS SDK")
    tools = {name: shutil.which(name) for name in ("clang", "swiftc", "ldid")}
    if not all(tools.values()):
        raise RuntimeError("existing clang, swiftc and ldid are required")
    resource = subprocess.check_output([tools["clang"], "--print-resource-dir"], text=True).strip()
    availability = Path(resource) / "lib/darwin/libclang_rt.ios.a"
    if not availability.is_file():
        raise RuntimeError("the installed clang iOS availability library is missing")
    build = ROOT / "build/native"
    build.mkdir(parents=True, exist_ok=True)
    stage = build / ("stage-%d-%d" % (int(time.time()), os.getpid()))
    stage.mkdir()
    shutil.copyfile(availability, stage / "libclang_rt.ios.a")
    steps = []
    activities_binary = build_activities(sdk, tools, build, stage, steps)
    settings_binary = build_settings(sdk, tools, build, stage, steps)
    browser_binary = build_browser(sdk, tools, build, stage, steps)
    alarms_binary = build_alarms(sdk, tools, build, stage, steps)
    source_files = sorted(file for file in (ROOT / "native").rglob("*") if file.is_file())
    manifest = {
        "project": "ios-control-bridge",
        "version": VERSION,
        "architecture": "arm64",
        "runtime_build_allowlist": ["20B101"],
        "built_at_unix": time.time(),
        "sdk": str(sdk),
        "binaries": {
            "icb-activities": {"sha256": digest(activities_binary)},
            "icb-settings": {"sha256": digest(settings_binary)},
            "icb-open-url": {"sha256": digest(browser_binary)},
            "icb-alarms": {"sha256": digest(alarms_binary)},
        },
        "binary_sha256": digest(activities_binary),
        "source_sha256": {str(file.relative_to(ROOT / "native")): digest(file) for file in source_files},
        "steps": steps,
    }
    # Replace only the project helpers after all compilation and signing steps pass.
    os.replace(activities_binary, build / "icb-activities")
    os.replace(settings_binary, build / "icb-settings")
    os.replace(browser_binary, build / "icb-open-url")
    os.replace(alarms_binary, build / "icb-alarms")
    (build / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf8")
    print(json.dumps(manifest))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
