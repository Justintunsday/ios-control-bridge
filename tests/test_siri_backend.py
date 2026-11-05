import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
import unittest
import uuid

from integrations.siri.backend import BackendError, OpenCodeHTTP, PROTOCOL, SiriBackend
from integrations.siri.server import MAX_FRAME, receive, send
from integrations.siri.install import replace_file


class FakeOpenCode:
    def __init__(self, mode="success"):
        self.mode, self.calls, self.accepted = mode, [], False
        self.answer = {"id": "asst_new", "type": "assistant", "content": [
            {"type": "reasoning", "text": "hidden reasoning"},
            {"type": "tool", "text": "private tool output"},
            {"type": "text", "text": "**你好，世界 😀**"}]}

    def call(self, method, path, body=None, timeout=6):
        assert 0 < timeout <= 6
        self.calls.append((method, path, body))
        if method == "POST" and path == "/api/session":
            return {"data": {"id": "ses_fixture"}}
        if method == "POST" and path.endswith("/prompt"):
            if self.mode == "ambiguous":
                raise BackendError("transport_unavailable", ambiguous=True)
            self.accepted = True
            return {}
        if method == "GET" and "/message/" in path:
            return {"data": self.answer}
        if method == "GET" and "/message?" in path:
            old = {"id": "asst_old", "type": "assistant", "content": [{"type": "text", "text": "old answer"}]}
            return {"data": [self.answer, old] if self.accepted else [old]}
        if method == "GET":
            if not self.accepted:
                return {"data": {"time": {"busy": 1, "idle": 1}, "outcome": "succeeded"}}
            if self.mode == "stale_outcome":
                return {"data": {"time": {"busy": 1, "idle": 1}, "outcome": "succeeded"}}
            return {"data": {"time": {"busy": 2, "idle": 1 if self.mode == "pending" else 3},
                             "outcome": "failed" if self.mode == "failed" else "succeeded"}}
        raise AssertionError((method, path))


class SiriBackendTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.state = Path(self.temporary.name) / "state.json"
        self.addCleanup(self.temporary.cleanup)

    def backend(self, http, unlocked=True):
        return SiriBackend(http, self.state, unlocked=lambda: unlocked, wait_seconds=.02, poll_seconds=.001)

    def question(self, text="测试中文与 emoji 😀", ident=None):
        return {"protocol": PROTOCOL, "id": ident or str(uuid.uuid4()), "op": "ask", "text": text}

    def test_locked_input_does_not_reach_opencode(self):
        http = FakeOpenCode()
        result = self.backend(http, False).handle(self.question())
        self.assertEqual(result["status"], "locked")
        self.assertEqual(http.calls, [])

    def test_new_answer_excludes_old_reasoning_and_tools(self):
        http = FakeOpenCode()
        question = self.question()
        result = self.backend(http).handle(question)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["text"], "你好，世界 😀")
        prompt = next(body for method, path, body in http.calls if path.endswith("/prompt"))
        self.assertTrue(prompt["text"].endswith(question["text"]))
        self.assertNotIn(question["text"], self.state.read_text())
        self.assertNotIn("hidden reasoning", self.state.read_text())

    def test_completed_request_recovery_never_resubmits(self):
        http = FakeOpenCode()
        question = self.question()
        self.assertEqual(self.backend(http).handle(question)["status"], "answered")
        self.assertEqual(self.backend(http).handle(question)["text"], "你好，世界 😀")
        self.assertEqual(sum(path.endswith("/prompt") for _, path, _ in http.calls), 1)

    def test_unknown_post_outcome_survives_restart_without_replay(self):
        http = FakeOpenCode("ambiguous")
        question = self.question()
        first = self.backend(http).handle(question)
        second = self.backend(http).handle(question)
        self.assertTrue(first["outcome_unknown"])
        self.assertTrue(second["outcome_unknown"])
        self.assertEqual(second["status"], "pending")
        self.assertEqual(sum(path.endswith("/prompt") for _, path, _ in http.calls), 1)

    def test_same_id_with_changed_text_is_rejected(self):
        http = FakeOpenCode()
        question = self.question()
        backend = self.backend(http)
        backend.handle(question)
        result = backend.handle(dict(question, text="different question"))
        self.assertEqual(result["reason"], "request_id_reused")
        self.assertEqual(sum(path.endswith("/prompt") for _, path, _ in http.calls), 1)

    def test_pending_or_stale_success_is_not_a_final_answer(self):
        for mode in ("pending", "stale_outcome"):
            with self.subTest(mode=mode):
                http = FakeOpenCode(mode)
                result = self.backend(http).handle(self.question())
                self.assertEqual(result["status"], "pending")
                self.assertNotIn("你好", result["text"])

    def test_failed_agent_does_not_return_preliminary_text(self):
        result = self.backend(FakeOpenCode("failed")).handle(self.question())
        self.assertEqual(result["status"], "error")
        self.assertNotIn("你好", result["text"])

    def test_invalid_requests_do_not_reach_opencode(self):
        http = FakeOpenCode()
        backend = self.backend(http)
        for request in [self.question("x" * 4097), self.question("\ud800"),
                        dict(self.question(), extra=True), dict(self.question(), id="bad"),
                        dict(self.question(), protocol="unknown")]:
            self.assertEqual(backend.handle(request)["status"], "error")
        self.assertEqual(http.calls, [])

    def test_new_session_with_no_busy_timestamps_is_accepted(self):
        class NewSession(FakeOpenCode):
            def call(self, method, path, body=None, timeout=6):
                result = super().call(method, path, body, timeout)
                if method == "GET" and "/message" not in path and not self.accepted:
                    result["data"]["time"] = {"created": 1}
                return result
        self.assertEqual(self.backend(NewSession()).handle(self.question())["status"], "answered")

    def test_malformed_server_data_returns_unavailable_without_prompt(self):
        class Malformed(FakeOpenCode):
            def call(self, method, path, body=None, timeout=6):
                result = super().call(method, path, body, timeout)
                if method == "GET":
                    result = {"data": {"time": {"busy": None, "idle": 0}}}
                return result
        http = Malformed()
        result = self.backend(http).handle(self.question())
        self.assertEqual(result["reason"], "invalid_response")
        self.assertFalse(any(path.endswith("/prompt") for _, path, _ in http.calls))

    def test_frames_preserve_unicode_and_reject_oversize_before_body(self):
        first, second = socket.socketpair()
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        payload = self.question()
        send(first, payload)
        self.assertEqual(receive(second), payload)
        first.sendall(struct.pack("!I", MAX_FRAME + 1))
        with self.assertRaises(ValueError):
            receive(second)

    def test_http_credentials_are_not_forwarded_to_redirect_target(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append((self.path, self.headers.get("Authorization")))
                self.send_response(302)
                self.send_header("Location", "/api/other")
                self.end_headers()
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            client = OpenCodeHTTP("http://127.0.0.1:" + str(server.server_port), "fixture-only")
            with self.assertRaises(BackendError):
                client.call("GET", "/api/info")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)
        self.assertEqual(received, [("/api/info", "Basic " + base64.b64encode(b"opencode:fixture-only").decode())])

    def test_install_replacement_preserves_the_open_signed_inode(self):
        original = Path(self.temporary.name) / "loaded.dylib"
        replacement = Path(self.temporary.name) / "signed.dylib"
        original.write_bytes(b"old mapped pages")
        replacement.write_bytes(b"new signed pages")
        # Windows locks open targets; verify inode behavior on the POSIX device instead.
        import os
        if os.name == "nt":
            replace_file(replacement, original, 0o755)
        else:
            with original.open("rb") as mapped:
                replace_file(replacement, original, 0o755)
                self.assertEqual(mapped.read(), b"old mapped pages")
        self.assertEqual(original.read_bytes(), b"new signed pages")


if __name__ == "__main__":
    unittest.main()
