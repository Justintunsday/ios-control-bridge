#!/usr/bin/env python3
"""Build the independent arm64 helper using an existing iPhoneOS toolchain."""
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
    source = ROOT / "native/activities"
    build = ROOT / "build/native"
    build.mkdir(parents=True, exist_ok=True)
    stage = build / ("stage-%d-%d" % (int(time.time()), os.getpid()))
    stage.mkdir()
    binary = stage / "icb-activities"
    steps = []
    steps.append(run([tools["clang"], "-target", "arm64-apple-ios16.1", "-isysroot", sdk,
                      "-fobjc-arc", "-fblocks", "-O2", "-Wall", "-Wextra", "-c",
                      source / "ActivityBridge.m", "-o", stage / "ActivityBridge.o"]))
    steps.append(run([tools["swiftc"], "-sdk", sdk, "-target", "arm64-apple-ios16.1",
                      "-swift-version", "5", "-Onone", "-module-cache-path", build / "ModuleCache",
                      "-import-objc-header", source / "ActivityBridge.h", source / "main.swift",
                      stage / "ActivityBridge.o", availability, "-o", binary]))
    steps.append(run([tools["ldid"], "-S" + str(source / "entitlements.plist"), binary], 10))
    binary.chmod(0o755)
    digest = lambda file: hashlib.sha256(file.read_bytes()).hexdigest()
    manifest = {"project": "ios-control-bridge", "version": "0.2.0", "architecture": "arm64",
                "runtime_build_allowlist": ["20B101"], "built_at_unix": time.time(), "sdk": str(sdk),
                "binary_sha256": digest(binary), "source_sha256": {
                    file.name: digest(file) for file in sorted(source.iterdir()) if file.is_file()},
                "steps": steps}
    # Replace only the project helper after all compilation and signing steps pass.
    os.replace(binary, build / "icb-activities")
    (build / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf8")
    print(json.dumps(manifest))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
