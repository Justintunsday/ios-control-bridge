#!/usr/bin/env python3
"""Run the actual native control flow with in-memory fixtures on a compatible iPhone.

Fixtures have no private entitlements and do not query or modify personal data.
The socket fixture uses a private temporary endpoint, never SpringBoard's socket.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ios_control_bridge import ellekit_bridge as bridge


def run(arguments):
    process = subprocess.run([str(item) for item in arguments], capture_output=True, text=True, timeout=30)
    if process.returncode:
        raise RuntimeError(process.stderr[-3000:] or "native tool failed")
    return process.stdout


def receive(stream):
    body = bytearray()
    while len(body) <= 4096:
        part = stream.recv(1)
        if not part: raise RuntimeError("socket closed before response")
        if part == b"\n":
            fields = body.decode("ascii").split()
            if len(fields) == 2: return {"protocol": fields[0], "generation": fields[1]}
            if len(fields) != 6: raise RuntimeError("invalid fixture frame")
            return {"generation": fields[0], "id": fields[1], "status": fields[2],
                    "value": int(fields[3]), "outcome_unknown": fields[4] == "1",
                    "detail": bytes.fromhex(fields[5]).decode() if fields[5] != "-" else ""}
        body.extend(part)
    raise RuntimeError("response too large")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk", default=os.environ.get("ICB_SDK", "/var/jb/opt/sdks/iPhoneOS16.5.sdk"))
    args = parser.parse_args()
    if sys.platform != "darwin": raise RuntimeError("run with the device Apple toolchain")
    clang, ldid = shutil.which("clang"), shutil.which("ldid")
    if not clang or not ldid: raise RuntimeError("existing clang and ldid are required")
    checks = {}
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    # Executables stay under the jailbreak prefix; only the socket uses /tmp.
    with tempfile.TemporaryDirectory(prefix="native-tests-", dir=str(build)) as temporary, \
            tempfile.TemporaryDirectory(prefix="icb-socket-", dir="/tmp") as socket_directory:
        stage = Path(temporary)
        endpoint_dir = Path(socket_directory) / "ipc"
        endpoint_dir.mkdir(mode=0o700)
        binaries = {}
        for name in ("Alarm", "Reminder", "Calendar", "Socket"):
            binary = stage / name
            command = [clang, "-target", "arm64-apple-ios16.1", "-isysroot", args.sdk,
                       "-fno-objc-arc", "-fblocks", "-Wall", "-Wextra",
                       ROOT / ("tests/native/%sRegression.m" % name), "-framework", "Foundation", "-o", binary]
            if name == "Socket": command.append('-DICB_DIRECTORY="%s"' % endpoint_dir)
            run(command)
            run([ldid, "-S", binary])
            binaries[name] = binary

        def fixture(component, mode, code, expected):
            process = subprocess.run([str(binaries[component]), mode], capture_output=True, text=True, timeout=5)
            assert process.returncode == code, (component, mode, process.returncode, process.stderr)
            payload = json.loads(process.stdout)
            for key, value in expected.items(): assert payload.get(key) == value, (component, mode, key, payload)
            checks[component.lower() + "_" + mode] = True
            return payload

        for component in ("Alarm", "Reminder"):
            fixture(component, "failure", 2, {"status": "partial", "reason": "readback_unavailable"})
            fixture(component, "absent", 0, {"deleted": True, "readback_complete": True})
            fixture(component, "present", 2, {"reason": "delete_not_confirmed"})
        created = "00000000-0000-4000-8000-000000000002"
        value = fixture("Reminder", "duplicate", 0, {"created_id": created})
        assert value["reminder"]["id"] == created
        fixture("Reminder", "missing_id", 3, {"reason": "created_identity_unavailable"})
        value = fixture("Calendar", "duplicate", 0, {"created_id": created})
        assert value["calendar"]["id"] == created
        page1 = fixture("Calendar", "page1", 2, {"count": 100, "total": 101, "truncated": True,
                                                 "complete_for_scope": False, "next_offset": 100})
        page2 = fixture("Calendar", "page2", 2, {"count": 1, "total": 101, "truncated": False,
                                                 "complete_for_scope": False, "next_offset": None})
        assert not ({row["id"] for row in page1["events"]} & {row["id"] for row in page2["events"]})
        fixture("Calendar", "wrong_time", 2, {"reason": "readback_mismatch"})
        value = fixture("Calendar", "event", 0, {"status": "verified"})
        assert value["event"]["notes"] == "fixture notes"

        endpoint = endpoint_dir / "spring.sock"
        process = None
        def stop():
            nonlocal process
            if process is not None:
                process.terminate()
                process.wait(timeout=5)
                process = None
        def start(delay=False):
            nonlocal process
            stop()
            process = subprocess.Popen([str(binaries["Socket"])] + (["delay"] if delay else []),
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
                        stream.settimeout(0.1)
                        stream.connect(str(endpoint))
                        return receive(stream)["generation"]
                except (OSError, RuntimeError): time.sleep(0.01)
            raise RuntimeError("socket fixture did not start")
        def raw(body=None, lifetime=2000, abandon=False):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
                stream.settimeout(2)
                stream.connect(str(endpoint))
                hello = receive(stream)
                if body is None:
                    body = {"protocol": bridge.PROTOCOL, "generation": hello["generation"],
                            "id": uuid.uuid4().hex, "action": "set_low_power", "value": 1,
                            "deadline_unix_ms": int(time.time() * 1000) + lifetime}
                wire = "%s %s %d %s %d\n" % (body["generation"], body["id"], body["deadline_unix_ms"],
                                              body["action"], body["value"])
                stream.sendall(wire.encode("ascii"))
                return body, None if abandon else receive(stream)

        try:
            with ExitStack() as stack:
                stack.enter_context(patch.object(bridge, "DIRECTORY", endpoint_dir))
                stack.enter_context(patch.object(bridge, "SOCKET_PATH", endpoint))
                stack.enter_context(patch.object(bridge, "_endpoint_owner", return_value=os.geteuid()))
                start(delay=True)
                _, expired = raw(lifetime=50)
                assert expired["status"] == "unavailable"
                assert bridge.request("get_orientation_lock")["value"] == 0
                checks["socket_expires_before_main_queue_execution"] = True
                start(delay=True)
                raw(abandon=True)
                time.sleep(0.6)
                assert bridge.request("get_orientation_lock")["value"] == 0
                checks["socket_disconnected_request_not_executed"] = True
                start()
                body, first = raw()
                _, repeated = raw(body)
                assert first["status"] == "ok" and repeated["detail"] == "duplicate_request"
                assert bridge.request("get_orientation_lock")["value"] == 1
                checks["socket_duplicate_request_not_replayed"] = True
                start()
                _, previous_generation = raw(body)
                assert previous_generation["status"] == "unavailable"
                assert bridge.request("get_orientation_lock")["value"] == 0
                checks["socket_old_generation_not_replayed"] = True
                with ThreadPoolExecutor(max_workers=4) as pool:
                    responses = list(pool.map(lambda _: bridge.request("set_low_power", 1), range(8)))
                assert all(value["status"] == "ok" for value in responses), responses
                assert len({value["id"] for value in responses}) == 8
                assert bridge.request("get_orientation_lock")["value"] == 8
                checks["socket_concurrent_clients_independent_serial_execution"] = True
                stop()
                (endpoint_dir / "spring.cmd").write_text("old\nset_low_power\n1\n")
                start()
                assert bridge.request("get_orientation_lock")["value"] == 0
                checks["socket_ignores_persistent_legacy_command"] = True
        finally: stop()
    print(json.dumps({"status": "passed", "scope": "native_fixture_no_personal_data_or_springboard_changes",
                      "checks": checks, "count": len(checks)}))


if __name__ == "__main__": main()
