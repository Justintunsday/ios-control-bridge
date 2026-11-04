from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge import ellekit_bridge


class ElleKitBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.command = self.directory / "spring.cmd"
        self.result = self.directory / "spring.result"
        self.command_tmp = self.directory / "spring.cmd.tmp"
        self.patches = [
            patch.object(ellekit_bridge, "DIRECTORY", self.directory),
            patch.object(ellekit_bridge, "COMMAND_PATH", self.command),
            patch.object(ellekit_bridge, "RESULT_PATH", self.result),
            patch.object(ellekit_bridge, "COMMAND_TMP", self.command_tmp),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in self.patches])
        self.addCleanup(self.temp.cleanup)

    def responder(self, response_status="ok", value=1, detail="test"):
        def loop():
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if self.command.is_file():
                    lines = self.command.read_text(encoding="utf8").splitlines()
                    if len(lines) >= 3:
                        self.result.write_text("%s\n%s\n%d\n%s\n" % (
                            lines[0], response_status, value, detail), encoding="utf8")
                        return
                time.sleep(0.02)
        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        return thread

    def test_request_round_trip(self):
        self.responder()
        output = ellekit_bridge.request("get_low_power", timeout=1)
        self.assertEqual(output["status"], "ok")
        self.assertEqual(output["value"], 1)
        self.assertEqual(output["detail"], "test")

    def test_disallowed_action_is_rejected_without_files(self):
        output = ellekit_bridge.request("run_selector", timeout=0.2)
        self.assertEqual(output["status"], "error")
        self.assertEqual(output["detail"], "unsupported_action")
        self.assertFalse(self.command.exists())

    def test_timeout(self):
        output = ellekit_bridge.request("get_low_power", timeout=0.2)
        self.assertEqual(output["status"], "unavailable")
        self.assertEqual(output["detail"], "bridge_timeout")


if __name__ == "__main__":
    unittest.main()
