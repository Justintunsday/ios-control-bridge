#!/usr/bin/env python3
"""Build BridgeChat with an installed iOS SDK, on iOS or macOS."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent
BUNDLE = "dev.ioscontrol.bridgechat"
VERSION = "0.4.0"
BUILD = "6"
MINIMUM_IOS = "16.1"
ICON_BASENAME = "AppIconNative60x60"


def run(arguments, timeout=180):
    result = subprocess.run(
        [str(value) for value in arguments],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr)[-18000:])
    return result.stdout.strip()


def copy_icons(app):
    for scale in (2, 3):
        source = ROOT / "Assets" / f"AppIcon60x60@{scale}x.png"
        data = source.read_bytes()
        size = scale * 60
        if (data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 26
                or int.from_bytes(data[16:20], "big") != size
                or int.from_bytes(data[20:24], "big") != size or data[25] != 2):
            raise ValueError(f"Expected an opaque RGB {size}px app icon: {source.name}")
        (app / f"{ICON_BASENAME}@{scale}x.png").write_bytes(data)


def ios_host():
    version = Path("/System/Library/CoreServices/SystemVersion.plist")
    if not version.is_file():
        return False
    name = plistlib.loads(version.read_bytes()).get("ProductName", "")
    return name in ("iPhone OS", "iOS", "iPadOS")


def sdk_version(sdk):
    for filename in ("SDKSettings.json", "SDKSettings.plist"):
        path = sdk / filename
        if path.is_file():
            data = (json.loads(path.read_text()) if path.suffix == ".json"
                    else plistlib.loads(path.read_bytes()))
            version = str(data.get("Version", ""))
            if re.fullmatch(r"\d+(?:\.\d+){0,2}", version):
                return version
    match = re.fullmatch(r"iPhone(?:OS|Simulator)(\d+(?:\.\d+){0,2})\.sdk", sdk.name)
    if match:
        return match.group(1)
    raise ValueError("Cannot determine the installed SDK version")


def app_info(simulator, version):
    return {
        "CFBundleIdentifier": BUNDLE,
        "CFBundleExecutable": "BridgeChat",
        "CFBundleName": "BridgeChat",
        "CFBundleDisplayName": "BridgeChat",
        "CFBundlePackageType": "APPL",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": BUILD,
        "CFBundleDevelopmentRegion": "zh_CN",
        "CFBundleSupportedPlatforms": ["iPhoneSimulator" if simulator else "iPhoneOS"],
        "MinimumOSVersion": MINIMUM_IOS,
        "UIDeviceFamily": [1],
        "LSRequiresIPhoneOS": True,
        "UILaunchScreen": {},
        "UIApplicationSceneManifest": {"UIApplicationSupportsMultipleScenes": False},
        "UISupportedInterfaceOrientations": ["UIInterfaceOrientationPortrait"],
        "CFBundleURLTypes": [{"CFBundleURLName": BUNDLE, "CFBundleURLSchemes": ["bridgechat"]}],
        "NSAppTransportSecurity": {"NSAllowsArbitraryLoads": True},
        "NSLocalNetworkUsageDescription": "连接你选择的 OpenCode 服务。",
        "CFBundleIcons": {
            "CFBundlePrimaryIcon": {
                "CFBundleIconFiles": [ICON_BASENAME],
                "UIPrerenderedIcon": False,
            },
        },
        "DTSDKName": ("iphonesimulator" if simulator else "iphoneos") + version,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("device", "simulator"), default="device")
    parser.add_argument("--sdk", type=Path)
    parser.add_argument("--simulator-id")
    parser.add_argument("--require-liquid-glass", action="store_true")
    args = parser.parse_args()
    simulator = args.platform == "simulator"
    on_ios = ios_host()
    if simulator and (on_ios or not args.simulator_id):
        parser.error("Simulator builds require macOS and --simulator-id")

    sdk_name = "iphonesimulator" if simulator else "iphoneos"
    selected = args.sdk or os.environ.get("ICB_SDK")
    if selected:
        sdk = Path(selected)
    elif not on_ios and shutil.which("xcrun"):
        sdk = Path(run(["xcrun", "--sdk", sdk_name, "--show-sdk-path"]))
    else:
        sdk = Path("/var/jb/opt/sdks/iPhoneOS16.5.sdk")
    if not sdk.is_dir():
        raise ValueError("An installed iPhoneOS SDK is required")
    version = sdk_version(sdk)
    compiler = shutil.which("swiftc")
    clang = shutil.which("clang")
    if not compiler or not clang:
        raise ValueError("An installed Swift compiler and clang are required")
    compiler_version = run([compiler, "--version"])
    match = re.search(r"Swift version (\d+)\.(\d+)", compiler_version)
    modern = int(version.split(".")[0]) >= 26
    if modern and (not match or tuple(map(int, match.groups())) < (6, 2)):
        raise ValueError("The iOS 26 SDK requires Swift 6.2 or newer")
    if args.require_liquid_glass and not modern:
        raise ValueError("A real iOS 26 or newer SDK is required for this build")

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work = ROOT / "build" / (stamp + "-" + args.platform)
    app = work / "Payload/BridgeChat.app"
    app.mkdir(parents=True)
    (app / "Info.plist").write_bytes(plistlib.dumps(app_info(simulator, version), sort_keys=False))
    copy_icons(app)

    architecture = platform.machine() if simulator else "arm64"
    target = architecture + "-apple-ios" + MINIMUM_IOS + ("-simulator" if simulator else "")
    flags = [
        "-sdk", str(sdk), "-target", target, "-swift-version", "5", "-parse-as-library",
        "-module-cache-path", str(ROOT / "build/ModuleCache" / args.platform),
        "-Xlinker", "-rpath", "-Xlinker", "/usr/lib/swift",
    ]
    if modern:
        flags += ["-D", "BRIDGECHAT_IOS26"]
    resource = Path(run([clang, "--print-resource-dir"]))
    availability = resource / "lib/darwin" / ("libclang_rt.iossim.a" if simulator else "libclang_rt.ios.a")
    if availability.is_file():
        flags.append(str(availability))

    test_binary = work / "ModelChecks"
    test_sources = [ROOT / "Sources/Models.swift", ROOT / "Sources/MessageText.swift", ROOT / "tests/ModelChecks.swift"]
    if on_ios or simulator:
        test_command = [compiler, *flags, "-Onone", *test_sources, "-o", test_binary]
    else:
        test_command = [compiler, "-swift-version", "5", "-parse-as-library", "-Onone", *test_sources, "-o", test_binary]
    run(test_command)
    if on_ios:
        run(["ldid", "-S", test_binary])
        test_binary.chmod(0o755)
    if simulator:
        run(["codesign", "--force", "--sign", "-", test_binary])
        checks = run(["xcrun", "simctl", "spawn", args.simulator_id, test_binary])
    else:
        checks = run([test_binary])
    if "12 native model checks passed" not in checks:
        raise RuntimeError("The native model checks did not report completion")
    print(checks, flush=True)

    executable = app / "BridgeChat"
    build_output = run([
        compiler, *flags, "-O", "-module-name", "BridgeChat",
        *sorted((ROOT / "Sources").glob("*.swift")), "-o", executable,
    ])
    (work / "compile.log").write_text(build_output)
    executable.chmod(0o755)
    entitlements = work / "entitlements.plist"
    entitlements.write_bytes(plistlib.dumps({
        "application-identifier": BUNDLE,
        "keychain-access-groups": [BUNDLE],
    }))
    if on_ios:
        run(["ldid", "-S" + str(entitlements), executable])
    else:
        signing = ["codesign", "--force", "--sign", "-"]
        if not simulator:
            signing += ["--entitlements", entitlements]
        run([*signing, app])
        run(["codesign", "--verify", "--strict", app])

    ipa = work / ("BridgeChat-" + VERSION + ("-simulator" if simulator else "") + ".ipa")
    with zipfile.ZipFile(ipa, "x", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((work / "Payload").rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(work).as_posix())

    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    record = {
        "bundle_id": BUNDLE, "version": VERSION, "build": BUILD,
        "ui_framework": "SwiftUI", "platform": args.platform,
        "minimum_ios": MINIMUM_IOS, "sdk_version": version,
        "swift_version": compiler_version.splitlines()[0],
        "liquid_glass_compiled": modern,
        "ipa": str(ipa), "ipa_sha256": sha(ipa),
        "app": str(app), "executable_sha256": sha(executable),
        "source_sha256": {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted((ROOT / "Sources").glob("*.swift"))},
        "build_script_sha256": sha(Path(__file__)),
        "native_model_checks_passed": 12,
        "model_checks_runtime": "iOS simulator" if simulator else "iOS device" if on_ios else "macOS",
        "icon_sha256": {path.name: sha(path) for path in sorted(app.glob(ICON_BASENAME + "*.png"))},
        "icon_source_sha256": sha(ROOT / "Assets/BridgeChatIcon.svg"),
        "compiled_at": dt.datetime.now(dt.timezone.utc).isoformat(), "stage": "built",
    }
    serialized = json.dumps(record, indent=2) + "\n"
    (work / "manifest.json").write_text(serialized)
    (ROOT / "build" / ("latest-" + args.platform + ".json")).write_text(serialized)
    (ROOT / "build/latest.json").write_text(serialized)
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
