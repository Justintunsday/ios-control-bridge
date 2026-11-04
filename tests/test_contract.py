from pathlib import Path
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ios_control_bridge.registry import invoke


class CLIContractTests(unittest.TestCase):
    def cli(self, *args):
        process = subprocess.run([sys.executable, str(ROOT / "bin/iosctl"), *args],
                                 capture_output=True, encoding="utf8", timeout=5)
        return process.returncode, json.loads(process.stdout)

    def test_capabilities_separate_plans_from_implementations(self):
        code, output = self.cli("capabilities")
        self.assertEqual(code, 0)
        rows = {row["name"]: row for row in output["data"]["operations"]}
        for name in ("device.info", "activities.get", "settings.get", "settings.set"):
            self.assertTrue(rows[name]["implemented"])
        self.assertEqual(rows["settings.get"]["supported_settings"], ["volume", "brightness"])
        for name in ("alarms.create", "reminders.create"):
            self.assertFalse(rows[name]["implemented"])
            self.assertFalse(rows[name]["runtime"]["ready_to_query"])

    def test_planned_write_cannot_fall_back_to_a_command(self):
        with patch("subprocess.run", side_effect=AssertionError("unexpected device command")):
            output = invoke("alarms.create", {"time": "07:00"})
        self.assertEqual(output["status"], "unavailable")
        self.assertEqual(output["reason"], "not_implemented")
        self.assertFalse(output["complete_for_scope"])

    def test_unsupported_setting_does_not_report_success_or_run_helper(self):
        with patch("subprocess.run", side_effect=AssertionError("unexpected device command")):
            output = invoke("settings.set", {"setting": "wifi", "value": False})
        self.assertEqual(output["status"], "unavailable")
        self.assertEqual(output["reason"], "unsupported_setting")
        self.assertFalse(output["complete_for_scope"])

    def test_invalid_json_is_machine_readable_error(self):
        code, output = self.cli("call", "alarms.create", "--params", "{")
        self.assertEqual(code, 4)
        self.assertEqual(output["status"], "error")
        self.assertNotIn("data", output)

    def test_parameters_must_be_an_object(self):
        code, output = self.cli("call", "device.info", "--params", "[]")
        self.assertEqual(code, 4)
        self.assertEqual(output["reason"], "parameters_must_be_object")

    def test_unknown_operation_does_not_report_success(self):
        code, output = self.cli("call", "settings.arbitrary_shell")
        self.assertEqual(code, 4)
        self.assertEqual(output["reason"], "unknown_operation")

    def test_request_id_survives_unavailable_operation(self):
        identifier = "debd4d72-1860-4d98-a3d0-c026ddbd1744"
        code, output = self.cli("call", "alarms.create", "--request-id", identifier)
        self.assertEqual(code, 3)
        self.assertEqual(output["request_id"], identifier)


if __name__ == "__main__":
    unittest.main()
