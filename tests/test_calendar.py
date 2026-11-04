from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge.calendar import (NATIVE_SCHEMA, NATIVE_SOURCE, create_calendar,
                                         delete_calendar, list_calendars)

VERSION = {"ProductVersion": "16.1.1", "ProductBuildVersion": "20B101"}
ID = "1DF0A9B7-6211-4FD8-A80A-03BEF357532A"


def calendar(**changes):
    value = {"id": ID, "title": "Test", "source": "iCloud", "source_id": "source",
             "allows_modifications": True}
    value.update(changes)
    return value


def payload(**changes):
    value = {"schema": NATIVE_SCHEMA, "source": NATIVE_SOURCE, "status": "verified",
             "observed_at_unix": 1.0}
    value.update(changes)
    return value


class CalendarBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.binary = Path(self.temp.name) / "icb-calendar"
        self.binary.touch()
        self.version = patch("ios_control_bridge.calendar.ios_version", return_value=VERSION)
        self.helper = patch("ios_control_bridge.calendar.helper_path", return_value=self.binary)
        self.version.start()
        self.helper.start()
        self.addCleanup(self.version.stop)
        self.addCleanup(self.helper.stop)
        self.addCleanup(self.temp.cleanup)

    def mock_run(self, helper_payload, exit_code=0):
        process = subprocess.CompletedProcess([], exit_code, json.dumps(helper_payload), "")
        return patch("ios_control_bridge.calendar.subprocess.run", return_value=process)

    def test_list(self):
        with self.mock_run(payload(calendars=[calendar()], count=1, sources=[])):
            output = list_calendars({})
        self.assertEqual(output["status"], "verified")
        self.assertEqual(output["data"]["calendars"][0]["title"], "Test")

    def test_create_and_readback(self):
        with self.mock_run(payload(calendar=calendar(title="New"))) as mocked:
            output = create_calendar({"title": "New"})
        self.assertEqual(output["status"], "verified")
        self.assertEqual(mocked.call_args.args[0][1:], ["create", "New"])

    def test_create_with_source(self):
        with self.mock_run(payload(calendar=calendar(title="New", source_id="src"))):
            output = create_calendar({"title": "New", "source_id": "src"})
        self.assertEqual(output["status"], "verified")

    def test_create_validation(self):
        self.assertEqual(create_calendar({})["reason"], "invalid_title")
        self.assertEqual(create_calendar({"title": ""})["reason"], "invalid_title")
        self.assertEqual(create_calendar({"title": "x", "source_id": 1})["reason"], "invalid_source_id")

    def test_create_readback_mismatch(self):
        with self.mock_run(payload(calendar=calendar(title="Other"))):
            output = create_calendar({"title": "New"})
        self.assertEqual(output["status"], "partial")
        self.assertEqual(output["reason"], "readback_mismatch")

    def test_delete(self):
        with self.mock_run(payload(deleted=True, calendar_id=ID)):
            output = delete_calendar({"calendar_id": ID})
        self.assertEqual(output["status"], "verified")

    def test_delete_invalid_id(self):
        self.assertEqual(delete_calendar({"calendar_id": "bad"})["reason"], "invalid_calendar_id")

    def test_unverified_build(self):
        with patch("ios_control_bridge.calendar.ios_version",
                   return_value={"ProductVersion": "17.0", "ProductBuildVersion": "other"}), \
             patch("ios_control_bridge.calendar.subprocess.run",
                   side_effect=AssertionError("unexpected helper")):
            output = list_calendars({})
        self.assertEqual(output["reason"], "unverified_os_build")


if __name__ == "__main__":
    unittest.main()
