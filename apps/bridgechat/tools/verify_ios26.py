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


def diagnostics(simulator):
    commands = {
        "app-info.txt": ["xcrun", "simctl", "appinfo", simulator, BUNDLE],
        "launch-log.txt": [
            "xcrun", "simctl", "spawn", simulator, "log", "show", "--last", "5m", "--style", "compact",
            "--predicate", 'process == "BridgeChat" OR eventMessage CONTAINS[c] "dev.ioscontrol.bridgechat"',
        ],
    }
    for name, command in commands.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=45)
            (OUTPUT / name).write_text((result.stdout + result.stderr)[-128000:])
        except (OSError, subprocess.TimeoutExpired) as error:
            (OUTPUT / name).write_text(str(error))


def capture(simulator, name, route, appearance, size, model):
    print("Reviewing " + name, flush=True)
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
    return {"name": name, "file": screenshot.name, "device": model, "process_alive": True}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    print("Building the iOS 26 device package", flush=True)
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
    run(["defaults", "write", "com.apple.iphonesimulator", "ConnectHardwareKeyboard", "-bool", "false"])
    simulator = run([
        "xcrun", "simctl", "create", "BridgeChat Liquid Glass",
        "com.apple.CoreSimulator.SimDeviceType.iPhone-17", runtime["identifier"],
    ])
    report = {"device_build": device, "simulator_runtime": runtime["version"], "screenshots": [], "sample_data": True}
    simulators = [simulator]
    try:
        print("Booting the iOS 26.2 simulator", flush=True)
        run(["xcrun", "simctl", "boot", simulator])
        run(["xcrun", "simctl", "bootstatus", simulator, "-b"], timeout=300)
        print("Building and testing the simulator package", flush=True)
        run([
            sys.executable, ROOT / "build.py", "--platform", "simulator", "--simulator-id", simulator,
            "--require-liquid-glass",
        ], timeout=600)
        sim = json.loads((ROOT / "build/latest-simulator.json").read_text())
        assert sim["native_model_checks_passed"] == 12
        shutil.copy2(ROOT / "build/latest-simulator.json", OUTPUT / "simulator-manifest.json")
        run(["xcrun", "simctl", "install", simulator, sim["app"]])
        run(["xcrun", "simctl", "status_bar", simulator, "override", "--time", "9:41", "--batteryState", "charged", "--batteryLevel", "100"])
        cases = [
            ("sessions-light", "sessions", "light", "large"),
            ("chat-light", "chat", "light", "large"),
            ("chat-dark", "chat", "dark", "large"),
            ("settings-light", "settings", "light", "large"),
            ("models-light", "models", "light", "large"),
            ("chat-accessibility", "chat", "light", "accessibility-extra-extra-large"),
            ("new-conversation", "new", "light", "large"),
            ("chat-running", "chat-running", "light", "large"),
            ("chat-keyboard", "chat-keyboard", "light", "large"),
            ("settings-accessibility", "settings", "light", "accessibility-extra-extra-large"),
        ]
        for name, route, appearance, size in cases:
            report["screenshots"].append(capture(simulator, name, route, appearance, size, "iPhone 17"))

        print("Checking a compact iPhone layout", flush=True)
        types = json.loads(run(["xcrun", "simctl", "list", "devicetypes", "--json"]))["devicetypes"]
        identifiers = {value["identifier"] for value in types}
        compact = None
        for name, suffix in (("iPhone SE (3rd generation)", "iPhone-SE-3rd-generation"), ("iPhone 13 mini", "iPhone-13-mini"), ("iPhone 16e", "iPhone-16e")):
            identifier = "com.apple.CoreSimulator.SimDeviceType." + suffix
            if identifier not in identifiers:
                continue
            try:
                compact = run(["xcrun", "simctl", "create", "BridgeChat Compact", identifier, runtime["identifier"]])
            except RuntimeError:
                continue
            report["compact_device"] = {"name": name, "device_type": identifier}
            break
        assert compact, "No supported compact iPhone simulator is installed"
        simulators.append(compact)
        run(["xcrun", "simctl", "shutdown", simulator])
        run(["xcrun", "simctl", "boot", compact])
        run(["xcrun", "simctl", "bootstatus", compact, "-b"], timeout=300)
        run(["xcrun", "simctl", "install", compact, sim["app"]])
        run(["xcrun", "simctl", "status_bar", compact, "override", "--time", "9:41", "--batteryState", "charged", "--batteryLevel", "100"])
        for name, route in (("sessions-compact", "sessions"), ("chat-compact", "chat"), ("keyboard-compact", "chat-keyboard")):
            report["screenshots"].append(capture(compact, name, route, "light", "large", report["compact_device"]["name"]))
        report["simulator_model_checks_passed"] = sim["native_model_checks_passed"]
        report["device_build_excludes_visual_fixtures"] = True
        report["real_glass_symbols_linked"] = True
    except Exception as error:
        report["error"] = str(error)
        diagnostics(simulators[-1])
        raise
    finally:
        (OUTPUT / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        for target in reversed(simulators):
            for operation in ("shutdown", "delete"):
                subprocess.run(["xcrun", "simctl", operation, target], capture_output=True, timeout=60)
    print(json.dumps({"version": device["version"], "sdk": device["sdk_version"], "screenshots": len(report["screenshots"])}))


if __name__ == "__main__":
    main()
