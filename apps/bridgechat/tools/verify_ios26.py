"""Build the real SDK-26 app and capture simulator-only visual fixtures."""
import json
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "dev.ioscontrol.bridgechat"
OUTPUT = ROOT / "build/ios26-review"


def run(arguments, timeout=240):
    result = subprocess.run(
        [str(value) for value in arguments], capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr)[-16000:])
    return result.stdout.strip()


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    run([sys.executable, ROOT / "build.py", "--require-liquid-glass"], timeout=600)
    device = json.loads((ROOT / "build/latest-device.json").read_text())
    executable = Path(device["app"]) / "BridgeChat"
    info = plistlib.loads((Path(device["app"]) / "Info.plist").read_bytes())
    assert device["liquid_glass_compiled"] and int(device["sdk_version"].split(".")[0]) >= 26
    assert not info.get("UIDesignRequiresCompatibility", False)
    assert b"--bridgechat-ui-review" not in executable.read_bytes()
    symbols = run(["nm", "-u", executable])
    assert "glassEffect" in symbols or "GlassEffectContainer" in symbols
    linked = run(["xcrun", "vtool", "-show-build", executable])
    assert re.search(r"sdk\s+26\.", linked), linked
    (OUTPUT / "linked-sdk.txt").write_text(linked + "\n")
    shutil.copy2(device["ipa"], OUTPUT / Path(device["ipa"]).name)
    shutil.copy2(ROOT / "build/latest-device.json", OUTPUT / "device-manifest.json")

    runtimes = json.loads(run(["xcrun", "simctl", "list", "runtimes", "--json"]))["runtimes"]
    runtime = next(value for value in runtimes if value.get("isAvailable") and value.get("version") == "26.2")
    simulator = run([
        "xcrun", "simctl", "create", "BridgeChat Liquid Glass",
        "com.apple.CoreSimulator.SimDeviceType.iPhone-17", runtime["identifier"],
    ])
    report = {"device_build": device, "simulator_runtime": runtime["version"], "screenshots": [], "sample_data": True}
    try:
        run(["xcrun", "simctl", "boot", simulator])
        run(["xcrun", "simctl", "bootstatus", simulator, "-b"], timeout=300)
        run([
            sys.executable, ROOT / "build.py", "--platform", "simulator", "--simulator-id", simulator,
            "--require-liquid-glass",
        ], timeout=600)
        sim = json.loads((ROOT / "build/latest-simulator.json").read_text())
        assert sim["native_model_checks_passed"] == 8
        run(["xcrun", "simctl", "install", simulator, sim["app"]])
        run(["xcrun", "simctl", "status_bar", simulator, "override", "--time", "9:41", "--batteryState", "charged", "--batteryLevel", "100"])
        cases = [
            ("sessions-light", "sessions", "light", "large"),
            ("chat-light", "chat", "light", "large"),
            ("chat-dark", "chat", "dark", "large"),
            ("settings-light", "settings", "light", "large"),
            ("models-light", "models", "light", "large"),
            ("chat-accessibility", "chat", "light", "accessibility-extra-extra-large"),
        ]
        for name, route, appearance, size in cases:
            run(["xcrun", "simctl", "ui", simulator, "appearance", appearance])
            run(["xcrun", "simctl", "ui", simulator, "content_size", size])
            launched = run([
                "xcrun", "simctl", "launch", "--terminate-running-process", simulator, BUNDLE,
                "--bridgechat-ui-review", route,
            ])
            pid = launched.rsplit(":", 1)[-1].strip()
            assert pid.isdigit(), launched
            time.sleep(5)
            processes = run(["xcrun", "simctl", "spawn", simulator, "launchctl", "list"])
            assert any(line.split() and line.split()[0] == pid for line in processes.splitlines()), name + " exited"
            screenshot = OUTPUT / (name + ".png")
            run(["xcrun", "simctl", "io", simulator, "screenshot", screenshot])
            report["screenshots"].append({"name": name, "file": screenshot.name, "process_alive": True})
        report["simulator_model_checks_passed"] = sim["native_model_checks_passed"]
        report["device_build_excludes_visual_fixtures"] = True
        report["real_glass_symbols_linked"] = True
        shutil.copy2(ROOT / "build/latest-simulator.json", OUTPUT / "simulator-manifest.json")
    finally:
        (OUTPUT / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        run(["xcrun", "simctl", "shutdown", simulator])
        run(["xcrun", "simctl", "delete", simulator])
    print(json.dumps({"version": device["version"], "sdk": device["sdk_version"], "screenshots": len(report["screenshots"])}))


if __name__ == "__main__":
    main()
