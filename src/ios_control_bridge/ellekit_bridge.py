"""Client for the optional ElleKit SpringBoard bridge.

The bridge is a tweak loaded into SpringBoard. It polls a line-based command
file and writes a line-based result file; only fixed actions are accepted.
"""
from pathlib import Path
import os
import time
import uuid

DIRECTORY = Path(os.environ.get("ICB_ELLEKIT_DIR", "/var/jb/var/lib/icb"))
BRIDGE_DYLIB = Path("/var/jb/usr/lib/TweakInject/icbridge.dylib")
COMMAND_PATH = DIRECTORY / "spring.cmd"
RESULT_PATH = DIRECTORY / "spring.result"
COMMAND_TMP = DIRECTORY / "spring.cmd.tmp"
ALLOWED_ACTIONS = {
    "get_low_power", "set_low_power",
    "get_orientation_lock", "set_orientation_lock",
    "get_wifi", "get_airplane", "get_bluetooth",
}
DEFAULT_TIMEOUT = 6.0


def available():
    return DIRECTORY.is_dir() and BRIDGE_DYLIB.is_file()


def request(action, value=0, timeout=DEFAULT_TIMEOUT):
    if action not in ALLOWED_ACTIONS:
        return {"status": "error", "detail": "unsupported_action"}
    if not DIRECTORY.is_dir():
        return {"status": "unavailable", "detail": "bridge_directory_missing"}
    request_id = uuid.uuid4().hex
    try:
        RESULT_PATH.unlink()
    except OSError:
        pass
    try:
        COMMAND_TMP.write_text("%s\n%s\n%d\n" % (request_id, action, int(value)), encoding="utf8")
        os.replace(COMMAND_TMP, COMMAND_PATH)
    except OSError:
        return {"status": "unavailable", "detail": "bridge_command_write_failed"}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            lines = RESULT_PATH.read_text(encoding="utf8").splitlines()
        except OSError:
            lines = []
        if len(lines) >= 3 and lines[0] == request_id:
            result = {"status": lines[1], "value": lines[2], "detail": lines[3] if len(lines) > 3 else ""}
            try:
                result["value"] = int(result["value"])
            except (TypeError, ValueError):
                result["value"] = -1
            return result
        time.sleep(0.05)
    return {"status": "unavailable", "detail": "bridge_timeout"}
