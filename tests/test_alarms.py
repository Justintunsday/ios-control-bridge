from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge.alarms import (NATIVE_SCHEMA, NATIVE_SOURCE, create_alarm,
                                       delete_alarm, list_alarms, set_enabled, update_alarm)

VERSION = {"ProductVersion": "16.1.1", "ProductBuildVersion": "20B101"}
ID = "1DF0A9B7-6211-4FD8-A80A-03BEF357532A"


def alarm(**changes):
    value = {"id": ID, "hour": 23, "minute": 59, "enabled": True, "sleep_alarm": False,
             "title": "Alarm", "repeat_schedule": 0, "next_fire_at_unix": 1000.0}
    value.update(changes)
    return value


def payload(**changes):
    value = {"schema": NATIVE_SCHEMA, "source": NATIVE_SOURCE, "status": "verified",
             "observed_at_unix": 1.0}
    value.update(changes)
    return value


class AlarmBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.binary = Path(self.temp.name) / "icb-alarms"
        self.binary.touch()
        self.version = patch("ios_control_bridge.alarms.ios_version", return_value=VERSION)
        self.helper = patch("ios_control_bridge.alarms.helper_path", return_value=self.binary)
        self.version.start()
        self.helper.start()
        self.addCleanup(self.version.stop)
        self.addCleanup(self.helper.stop)
        self.addCleanup(self.temp.cleanup)

    def mock_run(self, helper_payload, exit_code=0):
        process = subprocess.CompletedProcess([], exit_code, json.dumps(helper_payload), "")
        return patch("ios_control_bridge.alarms.subprocess.run", return_value=process)

    def test_list(self):
        with self.mock_run(payload(alarms=[alarm()], count=1)):
            output = list_alarms({})
        self.assertEqual(output["status"], "verified")
        self.assertEqual(output["data"]["alarms"][0]["hour"], 23)

    def test_list_rejects_parameters(self):
        self.assertEqual(list_alarms({"extra": True})["reason"], "unknown_parameters")

    def test_create_and_readback(self):
        with self.mock_run(payload(alarm=alarm(title="Test"))) as mocked:
            output = create_alarm({"hour": 23, "minute": 59, "title": "Test"})
        self.assertEqual(output["status"], "verified")
        self.assertEqual(mocked.call_args.args[0][1:], ["create", "23", "59", "Test"])

    def test_create_validation(self):
        self.assertEqual(create_alarm({"hour": 24, "minute": 0})["reason"], "invalid_hour")
        self.assertEqual(create_alarm({"hour": 1, "minute": 60})["reason"], "invalid_minute")
        self.assertEqual(create_alarm({"hour": 1, "minute": 0, "title": ""})["reason"], "invalid_title")

    def test_create_readback_mismatch_is_partial(self):
        with self.mock_run(payload(alarm=alarm(hour=22))):
            output = create_alarm({"hour": 23, "minute": 59})
        self.assertEqual(output["status"], "partial")
        self.assertEqual(output["reason"], "readback_mismatch")

    def test_update_fills_unspecified_values(self):
        responses = [
            subprocess.CompletedProcess([], 0, json.dumps(payload(alarms=[alarm(title="Old")])), ""),
            subprocess.CompletedProcess([], 0, json.dumps(payload(alarm=alarm(title="New"))), ""),
        ]
        with patch("ios_control_bridge.alarms.subprocess.run", side_effect=responses) as mocked:
            output = update_alarm({"alarm_id": ID, "title": "New"})
        self.assertEqual(output["status"], "verified")
        self.assertEqual(mocked.call_args_list[1].args[0][1:], ["update", ID, "23", "59", "New"])

    def test_update_requires_changes(self):
        self.assertEqual(update_alarm({"alarm_id": ID})["reason"], "no_changes")

    def test_update_unknown_alarm(self):
        with self.mock_run(payload(alarms=[])):
            output = update_alarm({"alarm_id": ID, "hour": 1})
        self.assertEqual(output["reason"], "alarm_not_found")

    def test_set_enabled_readback(self):
        with self.mock_run(payload(alarm=alarm(enabled=False))):
            output = set_enabled({"alarm_id": ID, "enabled": False})
        self.assertEqual(output["status"], "verified")

    def test_set_enabled_requires_bool(self):
        self.assertEqual(set_enabled({"alarm_id": ID, "enabled": 0})["reason"], "invalid_enabled")

    def test_delete(self):
        with self.mock_run(payload(deleted=True, alarm_id=ID, readback_complete=True)):
            output = delete_alarm({"alarm_id": ID})
        self.assertEqual(output["status"], "verified")

    def test_invalid_alarm_id(self):
        self.assertEqual(delete_alarm({"alarm_id": "not-a-uuid"})["reason"], "invalid_alarm_id")

    def test_delete_cannot_verify_without_complete_query(self):
        with self.mock_run(payload(deleted=True, alarm_id=ID)):
            self.assertEqual(delete_alarm({"alarm_id": ID})["reason"], "native_delete_inconsistent")
        with self.mock_run(payload(status="partial", reason="readback_unavailable"), exit_code=2):
            self.assertEqual(delete_alarm({"alarm_id": ID})["status"], "partial")

    def test_unverified_build_does_not_start_helper(self):
        with patch("ios_control_bridge.alarms.ios_version",
                   return_value={"ProductVersion": "17.0", "ProductBuildVersion": "other"}), \
             patch("ios_control_bridge.alarms.subprocess.run",
                   side_effect=AssertionError("unexpected helper")):
            output = list_alarms({})
        self.assertEqual(output["reason"], "unverified_os_build")


if __name__ == "__main__":
    unittest.main()
