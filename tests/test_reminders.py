from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge.reminders import (NATIVE_SCHEMA, NATIVE_SOURCE, complete_reminder,
                                          create_reminder, delete_reminder, list_lists,
                                          list_reminders, update_reminder)

VERSION = {"ProductVersion": "16.1.1", "ProductBuildVersion": "20B101"}
LIST = "170C82CB-4803-480C-BC15-8933C8C9F73E"
REMINDER = "5EF2FCAE-BAA7-4A20-8B7C-7614979CB647"


def payload(**changes):
    value = {"schema": NATIVE_SCHEMA, "source": NATIVE_SOURCE, "status": "verified",
             "observed_at_unix": 1.0}
    value.update(changes)
    return value


class RemindersBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.binary = Path(self.temp.name) / "icb-reminders"
        self.binary.touch()
        self.version = patch("ios_control_bridge.reminders.ios_version", return_value=VERSION)
        self.helper = patch("ios_control_bridge.reminders.helper_path", return_value=self.binary)
        self.version.start()
        self.helper.start()
        self.addCleanup(self.version.stop)
        self.addCleanup(self.helper.stop)
        self.addCleanup(self.temp.cleanup)

    def mock_run(self, helper_payload, exit_code=0):
        process = subprocess.CompletedProcess([], exit_code, json.dumps(helper_payload), "")
        return patch("ios_control_bridge.reminders.subprocess.run", return_value=process)

    def test_lists(self):
        with self.mock_run(payload(lists=[{"id": LIST, "name": "Reminders", "reminder_count": 1}],
                                   count=1)):
            output = list_lists({})
        self.assertEqual(output["status"], "verified")

    def test_list(self):
        with self.mock_run(payload(reminders=[{"id": REMINDER, "title": "test",
                                               "completed": False, "list_id": LIST}], count=1)):
            output = list_reminders({"list_id": LIST})
        self.assertEqual(output["status"], "verified")
        self.assertEqual(output["data"]["reminders"][0]["title"], "test")

    def test_create_readback(self):
        with self.mock_run(payload(created_id=REMINDER, reminder={"id": REMINDER, "title": "New",
                                             "completed": False, "list_id": LIST})):
            output = create_reminder({"list_id": LIST, "title": "New"})
        self.assertEqual(output["status"], "verified")

    def test_update_readback(self):
        with self.mock_run(payload(reminder={"id": REMINDER, "title": "New",
                                             "completed": False, "list_id": LIST})):
            output = update_reminder({"reminder_id": REMINDER, "title": "New"})
        self.assertEqual(output["status"], "verified")

    def test_complete_readback(self):
        with self.mock_run(payload(reminder={"id": REMINDER, "title": "test",
                                             "completed": True, "list_id": LIST})):
            output = complete_reminder({"reminder_id": REMINDER})
        self.assertEqual(output["status"], "verified")

    def test_delete(self):
        with self.mock_run(payload(deleted=True, reminder_id=REMINDER, readback_complete=True)):
            output = delete_reminder({"reminder_id": REMINDER})
        self.assertEqual(output["status"], "verified")

    def test_create_rejects_wrong_list_or_created_identity(self):
        row = {"id": REMINDER, "title": "New", "list_id": LIST}
        for changes in ({"created_id": LIST}, {"created_id": REMINDER,
                         "reminder": {**row, "list_id": REMINDER}}):
            native = payload(reminder=row)
            native.update(changes)
            with self.mock_run(native):
                self.assertEqual(create_reminder({"list_id": LIST, "title": "New"})["status"], "partial")

    def test_delete_requires_complete_readback(self):
        with self.mock_run(payload(deleted=True, reminder_id=REMINDER)):
            self.assertEqual(delete_reminder({"reminder_id": REMINDER})["reason"], "native_delete_inconsistent")
        with self.mock_run(payload(status="partial", reason="readback_unavailable"), exit_code=2):
            self.assertEqual(delete_reminder({"reminder_id": REMINDER})["status"], "partial")

    def test_invalid_uuid(self):
        self.assertEqual(list_reminders({"list_id": "bad"})["reason"], "invalid_list_id")

    def test_invalid_title(self):
        self.assertEqual(create_reminder({"list_id": LIST, "title": ""})["reason"], "invalid_title")

    def test_unverified_build_does_not_start_helper(self):
        with patch("ios_control_bridge.reminders.ios_version",
                   return_value={"ProductVersion": "17.0", "ProductBuildVersion": "other"}), \
             patch("ios_control_bridge.reminders.subprocess.run",
                   side_effect=AssertionError("unexpected helper")):
            output = list_lists({})
        self.assertEqual(output["reason"], "unverified_os_build")


if __name__ == "__main__":
    unittest.main()
