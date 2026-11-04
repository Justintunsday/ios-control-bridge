#!/usr/bin/env python3
"""Build and install the optional ElleKit SpringBoard bridge (run as root on device).

The bridge is an arm64e tweak loaded into SpringBoard. It is not part of the
Debian package; it is an explicit jailbreak extension for settings that require
SpringBoard context (low power mode, orientation lock, read-only network state).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TWEAK_DIR = Path("/var/jb/usr/lib/TweakInject")
COMMAND_DIR = Path("/var/jb/var/lib/icb")
DEFAULT_SDK = Path("/var/jb/opt/sdks/iPhoneOS16.5.sdk")


def run(args, seconds=180):
    process = subprocess.run([str(arg) for arg in args], capture_output=True, text=True,
                             timeout=seconds, check=False)
    if process.returncode != 0:
        raise RuntimeError("%s failed: %s" % (args[0], process.stderr[-4000:]))
    return {"tool": Path(str(args[0])).name, "exit": process.returncode,
            "stdout": process.stdout[-2000:], "stderr": process.stderr[-4000:]}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk", default=os.environ.get("ICB_SDK", str(DEFAULT_SDK)))
    parser.add_argument("--respring", action="store_true",
                        help="restart SpringBoard after installation")
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise RuntimeError("build requires the device Apple toolchain")
    if os.geteuid() != 0:
        raise RuntimeError("run as root: sudo python3 tools/build_ellekit_bridge.py")
    sdk = Path(args.sdk)
    if not sdk.is_dir():
        raise RuntimeError("set ICB_SDK or --sdk to an installed iPhoneOS SDK")
    tools = {name: shutil.which(name) for name in ("clang", "ldid")}
    if not all(tools.values()):
        raise RuntimeError("clang and ldid are required")
    source = ROOT / "native/ellekit"
    binary = Path("/tmp/icbridge-%d.dylib" % os.getpid())
    steps = [
        run([tools["clang"], "-target", "arm64e-apple-ios16.1", "-isysroot", sdk,
             "-dynamiclib", "-fno-objc-arc", "-O1", "-Wall",
             source / "SpringBridge.m", "-framework", "Foundation", "-o", binary]),
        run([tools["ldid"], "-S", binary], 20),
    ]
    TWEAK_DIR.mkdir(parents=True, exist_ok=True)
    COMMAND_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(COMMAND_DIR, 0o777)
    destination = TWEAK_DIR / "icbridge.dylib"
    os.replace(binary, destination)
    os.chmod(destination, 0o755)
    os.chown(destination, 0, 0)
    plist = plistlib.loads((source / "icbridge.plist").read_bytes())
    plist_path = TWEAK_DIR / "icbridge.plist"
    plist_path.write_bytes(plistlib.dumps(plist, fmt=plistlib.FMT_BINARY))
    os.chmod(plist_path, 0o644)
    os.chown(plist_path, 0, 0)
    if args.respring:
        subprocess.run(["/var/jb/usr/bin/killall", "-9", "SpringBoard"], check=False)
    manifest = {
        "project": "ios-control-bridge",
        "component": "ellekit-springbridge",
        "built_at_unix": time.time(),
        "sdk": str(sdk),
        "binary": str(destination),
        "binary_sha256": digest(destination),
        "plist": str(plist_path),
        "command_directory": str(COMMAND_DIR),
        "source_sha256": {
            "SpringBridge.m": digest(source / "SpringBridge.m"),
            "icbridge.plist": digest(source / "icbridge.plist"),
        },
        "steps": steps,
        "respring_requested": bool(args.respring),
    }
    print(json.dumps(manifest))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
