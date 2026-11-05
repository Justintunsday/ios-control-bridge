from contextlib import ExitStack
from pathlib import Path
import socket
import stat
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge import ellekit_bridge as bridge

GENERATION = "00000000000040008000000000000001"


class ConnectedSocket:
    """An already-connected stream pair, retaining real send/receive behavior."""
    def __init__(self, stream): self.stream = stream
    def __enter__(self): return self
    def __exit__(self, *args): self.stream.close()
    def connect(self, address): pass
    def settimeout(self, seconds): self.stream.settimeout(seconds)
    def sendall(self, data): self.stream.sendall(data)
    def recv(self, count): return self.stream.recv(count)
    def fileno(self): return self.stream.fileno()


def line(stream):
    data = bytearray()
    while True:
        part = stream.recv(1)
        if not part: raise EOFError()
        if part == b"\n": return data.decode("ascii").split()
        data.extend(part)


class ElleKitBridgeTests(unittest.TestCase):
    def setUp(self):
        family = patch.object(bridge.socket, "AF_UNIX", getattr(socket, "AF_UNIX", socket.AF_INET), create=True)
        family.start()
        self.addCleanup(family.stop)

    def responder(self, *, changes=None, delay=0, requests=None):
        client, server = socket.socketpair()
        self.addCleanup(client.close)
        def reply():
            with server:
                server.settimeout(1)
                try:
                    server.sendall((bridge.PROTOCOL + " " + GENERATION + "\n").encode())
                    fields = line(server)
                    request = {"generation": fields[0], "id": fields[1], "deadline_unix_ms": int(fields[2]),
                               "action": fields[3], "value": int(fields[4])}
                    if requests is not None: requests.append(request)
                    time.sleep(delay)
                    response = {"protocol": bridge.PROTOCOL, "generation": GENERATION,
                                "id": request["id"], "status": "ok", "value": request["value"],
                                "detail": "fixture", "outcome_unknown": False}
                    response.update(changes or {})
                    wire = "%s %s %s %s %d %s\n" % (response["generation"], response["id"], response["status"],
                            response["value"], 1 if response["outcome_unknown"] else 0, response["detail"].encode().hex())
                    server.sendall(wire.encode())
                except (OSError, EOFError): pass
        thread = threading.Thread(target=reply, daemon=True)
        thread.start()
        self.addCleanup(lambda: thread.join(2))
        return ConnectedSocket(client)

    def call(self, action="get_low_power", value=1, changes=None, delay=0):
        stream = self.responder(changes=changes, delay=delay)
        with patch.object(bridge, "_secure_endpoint", return_value=501), \
             patch.object(bridge, "_peer_uid", return_value=501), \
             patch.object(bridge.socket, "socket", return_value=stream) as factory:
            output = bridge.request(action, value, timeout=0.1)
        self.assertEqual(factory.call_count, 1)
        return output

    def test_request_round_trip(self):
        output = self.call()
        self.assertEqual(output["status"], "ok")
        self.assertEqual(output["value"], 1)
        self.assertFalse(output["outcome_unknown"])

    def test_wrong_peer_never_receives_a_command(self):
        requests = []
        stream = self.responder(requests=requests)
        with patch.object(bridge, "_secure_endpoint", return_value=501), \
             patch.object(bridge, "_peer_uid", return_value=123), \
             patch.object(bridge.socket, "socket", return_value=stream):
            output = bridge.request("set_low_power", 1)
        self.assertEqual(output["detail"], "bridge_peer_rejected")
        self.assertEqual(requests, [])

    def test_response_identity_generation_and_value_are_checked(self):
        for changes in ({"id": "wrong"}, {"generation": "wrong"}, {"value": "invalid"}):
            self.assertEqual(self.call(changes=changes)["status"], "unavailable")

    def test_timeout_after_write_is_unknown_and_is_not_retried(self):
        output = self.call("set_low_power", delay=0.2)
        self.assertEqual(output["status"], "unavailable")
        self.assertTrue(output["outcome_unknown"])

    def test_server_execution_uncertainty_is_preserved(self):
        output = self.call("set_low_power", changes={"status": "unavailable", "outcome_unknown": True})
        self.assertTrue(output["outcome_unknown"])

    def test_no_persistent_command_or_aliased_file_is_written(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            victim = directory / "config"
            victim.write_text("untouched", encoding="utf8")
            try: (directory / "spring.cmd.tmp").symlink_to(victim)
            except OSError:
                import os
                os.link(victim, directory / "spring.cmd.tmp")
            with patch.object(bridge, "DIRECTORY", directory):
                self.assertEqual(self.call()["status"], "ok")
            self.assertEqual(victim.read_text(encoding="utf8"), "untouched")
            self.assertFalse((directory / "spring.cmd").exists())

    def test_concurrent_clients_have_independent_responses(self):
        requests, outputs = [], []
        streams = [self.responder(requests=requests) for _ in range(6)]
        with patch.object(bridge, "_secure_endpoint", return_value=501), \
             patch.object(bridge, "_peer_uid", return_value=501), \
             patch.object(bridge.socket, "socket", side_effect=streams):
            workers = [threading.Thread(target=lambda: outputs.append(bridge.request("get_low_power")))
                       for _ in streams]
            for worker in workers: worker.start()
            for worker in workers: worker.join(2)
        self.assertEqual(len(outputs), 6)
        self.assertTrue(all(output["status"] == "ok" for output in outputs))
        self.assertEqual(len({request["id"] for request in requests}), 6)

    def test_unsupported_or_insecure_endpoint_never_connects(self):
        with patch.object(bridge.socket, "socket", side_effect=AssertionError("unexpected connection")):
            self.assertEqual(bridge.request("set_bluetooth")["detail"], "unsupported_action")
            self.assertEqual(bridge.request("get_wifi", timeout=0)["detail"], "invalid_request")
            with patch.object(bridge, "_secure_endpoint", return_value=None):
                self.assertEqual(bridge.request("get_wifi")["status"], "unavailable")

    def test_endpoint_rejects_symlinks_unsafe_modes_and_foreign_owner(self):
        directory = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=501)
        endpoint = SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600, st_uid=501)
        cases = [(directory, endpoint, 501),
                 (SimpleNamespace(st_mode=stat.S_IFLNK | 0o700, st_uid=501), endpoint, None),
                 (SimpleNamespace(st_mode=stat.S_IFDIR | 0o777, st_uid=501), endpoint, None),
                 (directory, SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=501), None),
                 (directory, SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600, st_uid=123), None)]
        for directory_info, socket_info, expected in cases:
            with patch.object(bridge, "_endpoint_owner", return_value=501), \
                 patch.object(Path, "lstat", side_effect=[directory_info, socket_info]):
                self.assertEqual(bridge._secure_endpoint(), expected)


if __name__ == "__main__": unittest.main()
