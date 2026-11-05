"""Install/disable the optional native Siri adapter on the verified rootless device.

Build NativeBridge.dylib with build-siri on macOS first. No on-device compilation.
Existing installations are preserved unless their hashes match our manifest.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid

SOURCE = Path(__file__).resolve().parent
BASE = Path("/var/jb/var/root/.local/share/ios-control-siri")
DIRECTORY = Path("/var/mobile/Library/Assistant/ICBSiriBridge")
TWEAK = Path("/var/jb/usr/lib/TweakInject/ICBSiriNativeBridge.dylib")
FILTER = TWEAK.with_suffix(".plist")
JOB = Path("/var/jb/Library/LaunchDaemons/dev.ioscontrol.siri.plist")
MANIFEST = BASE / "installation.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    return subprocess.run([str(arg) for arg in args], check=True, capture_output=True,
                          timeout=15, text=True)


def replace_file(source, target, mode):
    # A fresh inode is mandatory: mutating a mapped signed dylib causes invalid pages.
    fd, name = tempfile.mkstemp(prefix=".icb-siri-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(source.read_bytes())
        os.chmod(name, mode)
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def require_owned(path, uid, mode=None):
    info = path.lstat()
    if path.is_symlink() or info.st_uid != uid or (mode is not None and stat.S_IMODE(info.st_mode) != mode):
        raise RuntimeError("unexpected owner or mode: " + str(path))


def status():
    if not (DIRECTORY / "bridge.sock").exists():
        return False
    from server import receive, send
    try:
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(3)
            connection.connect(str(DIRECTORY / "bridge.sock"))
            send(connection, {"protocol": "ios-control-bridge.siri.v1", "id": str(uuid.uuid4()), "op": "status"})
            return receive(connection).get("status") == "ready"
    except (OSError, EOFError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "disable", "enable"))
    parser.add_argument("--library", type=Path)
    parser.add_argument("--password-file", type=Path)
    parser.add_argument("--origin", default="http://127.0.0.1:4097")
    parser.add_argument("--model", help="provider/model; otherwise use OpenCode's configured default")
    parser.add_argument("--project-directory")
    args = parser.parse_args()
    if sys.platform != "darwin" or os.geteuid() != 0:
        raise SystemExit("run as root on the verified iOS device")
    import pwd
    build = run(["sysctl", "-n", "kern.osversion"]).stdout.strip()
    if build != "20B101":
        raise SystemExit("native Siri supports only the verified iOS 16.1.1 / 20B101 build")
    mobile = pwd.getpwnam("mobile")
    flag = DIRECTORY / "enabled"
    if args.action == "disable":
        if flag.exists() or flag.is_symlink():
            require_owned(flag, mobile.pw_uid, 0o600)
            flag.unlink()
        print("Siri routing disabled. OpenCode tasks already accepted may continue in the app.")
        return
    if args.action == "enable":
        require_owned(DIRECTORY, mobile.pw_uid, 0o700)
        require_owned(MANIFEST, 0, 0o600)
        installation = json.loads(MANIFEST.read_text())
        if any(digest(Path(path)) != sha for path, sha in installation["files"].items()):
            raise RuntimeError("installed Siri files differ from the manifest")
        events = DIRECTORY / "native-events.jsonl"
        if not events.is_file() or events.is_symlink():
            raise RuntimeError("native Siri hook readiness has not been observed")
        ready = any(row.get("event") == "bridge_ready" and row.get("unix", 0) >= installation["started_at"]
                    for row in (json.loads(line) for line in events.read_text().splitlines()))
        if not ready:
            raise RuntimeError("native Siri hook ABI did not become ready")
        if not status():
            raise RuntimeError("local Siri service is not ready")
        if flag.exists() or flag.is_symlink():
            require_owned(flag, mobile.pw_uid, 0o600)
        else:
            flag.touch(mode=0o600)
            os.chown(flag, mobile.pw_uid, mobile.pw_gid)
        print("Siri routing enabled. Use stock Siri to verify actual display and speech.")
        return
    if not args.library or not args.password_file:
        parser.error("install requires --library and --password-file")
    from backend import OpenCodeHTTP
    from server import private_bytes
    private_bytes(args.password_file, 4096)
    OpenCodeHTTP(args.origin, "validation-only")
    model = None
    if args.model:
        provider, separator, name = args.model.partition("/")
        if not separator or not provider or not name:
            parser.error("--model must be provider/model")
        model = {"providerID": provider, "id": name}
    if MANIFEST.exists():
        raise RuntimeError("installation already exists; disable it before reviewing an explicit upgrade")
    # Fresh install only; never take over another tweak or launchd job.
    if any(path.exists() or path.is_symlink() for path in (TWEAK, FILTER, JOB)):
        raise RuntimeError("pre-existing Siri files were preserved; review them before installation")
    BASE.mkdir(parents=True, mode=0o700, exist_ok=True)
    require_owned(BASE, 0, 0o700)
    if not DIRECTORY.exists():
        DIRECTORY.mkdir(mode=0o700)
        os.chown(DIRECTORY, mobile.pw_uid, mobile.pw_gid)
    require_owned(DIRECTORY, mobile.pw_uid, 0o700)
    if flag.exists() or flag.is_symlink():
        raise RuntimeError("pre-existing Siri enable flag was preserved")
    release = BASE / ("release-" + uuid.uuid4().hex)
    release.mkdir(mode=0o700)
    for name in ("backend.py", "server.py"):
        shutil.copyfile(SOURCE / name, release / name)
    config = {"origin": args.origin, "password_file": str(args.password_file.resolve()),
              "socket_directory": str(DIRECTORY), "state_file": str(BASE / "state.json"),
              "wait_seconds": 20}
    if model:
        config["model"] = model
    if args.project_directory:
        config["project_directory"] = args.project_directory
    config_file = release / "config.json"
    config_file.write_text(json.dumps(config), encoding="utf8")
    config_file.chmod(0o600)
    prepared = release / "NativeBridge.dylib"
    shutil.copyfile(args.library, prepared)
    run(["ldid", "-S", prepared])
    data = {"Label": "dev.ioscontrol.siri", "ProgramArguments": [sys.executable, "-B",
            str(release / "server.py"), "--config", str(config_file)], "RunAtLoad": True,
            "KeepAlive": True, "ThrottleInterval": 10, "WorkingDirectory": str(release),
            "EnvironmentVariables": {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
            "StandardOutPath": str(release / "stdout.log"), "StandardErrorPath": str(release / "stderr.log")}
    prepared_job = release / "job.plist"
    prepared_job.write_bytes(plistlib.dumps(data))
    prepared_filter = release / "filter.plist"
    prepared_filter.write_bytes(plistlib.dumps({"Filter": {"Executables": ["assistantd"]}}))
    installed = []
    try:
        for source, target, mode in ((prepared, TWEAK, 0o755), (prepared_filter, FILTER, 0o644), (prepared_job, JOB, 0o644)):
            replace_file(source, target, mode)
            installed.append((target, digest(target)))
        run(["launchctl", "bootstrap", "system", JOB])
        for _ in range(20):
            if status():
                break
            time.sleep(.25)
        else:
            raise RuntimeError("Siri backend did not become ready")
        # No SpringBoard restart. A timeout does not by itself mean assistantd failed.
        started_at = int(time.time())
        try:
            run(["launchctl", "kickstart", "-k", "system/com.apple.assistantd"])
        except subprocess.TimeoutExpired:
            pass
        MANIFEST.write_text(json.dumps({"files": {str(path): sha for path, sha in installed},
            "release": str(release), "build": build, "started_at": started_at}), encoding="utf8")
        MANIFEST.chmod(0o600)
        print("Installed with routing disabled. Verify bridge_ready in native-events.jsonl, then run enable.")
    except BaseException:
        subprocess.run(["launchctl", "bootout", "system/dev.ioscontrol.siri"], capture_output=True, timeout=15)
        for target, sha in installed:
            if target.is_file() and not target.is_symlink() and digest(target) == sha:
                target.unlink()
        raise


if __name__ == "__main__":
    main()
