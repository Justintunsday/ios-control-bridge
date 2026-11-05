from pathlib import Path
import json
import subprocess
import sys
import tempfile
from datetime import datetime
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge.calendar import (NATIVE_SCHEMA, NATIVE_SOURCE, create_calendar,
                                         create_event, delete_calendar, delete_event,
                                         list_calendars, list_events)

VERSION = {"ProductVersion": "16.1.1", "ProductBuildVersion": "20B101"}
ID = "1DF0A9B7-6211-4FD8-A80A-03BEF357532A"
EVENT_ID = "2DF0A9B7-6211-4FD8-A80A-03BEF357532A"
START = "2026-11-05T10:00:00Z"
END = "2026-11-05T11:00:00Z"


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
        with self.mock_run(payload(calendar=calendar(title="New"), created_id=ID)) as mocked:
            output = create_calendar({"title": "New"})
        self.assertEqual(output["status"], "verified")
        self.assertEqual(mocked.call_args.args[0][1:], ["create", "New"])

    def test_create_with_source(self):
        with self.mock_run(payload(calendar=calendar(title="New", source_id="src"), created_id=ID)):
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

    def test_list_events(self):
        event = {"id": EVENT_ID, "title": "Event", "calendar_id": ID, "start": 1.0,
                 "end": 2.0, "all_day": False}
        with self.mock_run(payload(events=[event], count=1, limit=100, offset=0,
                                   truncated=False, complete_for_scope=True)):
            output = list_events({"calendar_id": ID, "start": START, "end": END})
        self.assertEqual(output["status"], "verified")
        self.assertEqual(output["data"]["events"][0]["id"], EVENT_ID)

    def test_list_events_rejects_bad_range(self):
        output = list_events({"calendar_id": ID, "start": END, "end": START})
        self.assertEqual(output["reason"], "invalid_date_range")

    def test_create_event(self):
        event = {"id": EVENT_ID, "title": "Event", "calendar_id": ID,
                 "start": datetime.fromisoformat(START.replace("Z", "+00:00")).timestamp(),
                 "end": datetime.fromisoformat(END.replace("Z", "+00:00")).timestamp(),
                 "all_day": False, "notes": ""}
        with self.mock_run(payload(event=event)):
            output = create_event({"calendar_id": ID, "title": "Event", "start": START, "end": END})
        self.assertEqual(output["status"], "verified")

    def test_create_event_validation(self):
        self.assertEqual(create_event({"calendar_id": ID, "title": "", "start": START,
                                       "end": END})["reason"], "invalid_title")
        self.assertEqual(create_event({"calendar_id": ID, "title": "x", "start": "bad",
                                       "end": END})["reason"], "invalid_start")

    def test_delete_event(self):
        with self.mock_run(payload(deleted=True, event_id=EVENT_ID)):
            output = delete_event({"event_id": EVENT_ID})
        self.assertEqual(output["status"], "verified")

    def test_create_rejects_old_identity_or_wrong_source(self):
        for changes in ({"created_id": EVENT_ID}, {"created_id": ID}):
            with self.mock_run(payload(calendar=calendar(title="New", source_id="other"), **changes)):
                output = create_calendar({"title": "New", "source_id": "requested"})
            self.assertEqual(output["reason"], "readback_mismatch")
        with self.mock_run(payload(calendar=calendar(title="New"), created_id=EVENT_ID)):
            self.assertEqual(create_calendar({"title": "New"})["status"], "partial")

    def test_truncated_events_remain_partial_and_keep_pagination(self):
        with self.mock_run(payload(status="partial", events=[{"id": "event"}], count=1, total=2,
                                   limit=1, offset=0, truncated=True, complete_for_scope=False,
                                   next_offset=1), exit_code=2):
            output = list_events({"calendar_id": ID, "start": START, "end": END, "limit": 1})
        self.assertEqual(output["status"], "partial")
        self.assertFalse(output["complete_for_scope"])
        self.assertEqual(output["data"]["next_offset"], 1)

    def test_missing_or_inconsistent_completeness_is_rejected(self):
        for extra in ({}, {"limit": 100, "offset": 0, "truncated": True, "complete_for_scope": True}):
            with self.mock_run(payload(events=[], **extra)):
                output = list_events({"calendar_id": ID, "start": START, "end": END})
            self.assertEqual(output["reason"], "native_completeness_invalid")

    def test_event_time_and_notes_must_match_readback(self):
        start = datetime.fromisoformat(START.replace("Z", "+00:00")).timestamp()
        end = datetime.fromisoformat(END.replace("Z", "+00:00")).timestamp()
        event = {"id": EVENT_ID, "title": "Event", "calendar_id": ID, "start": start,
                 "end": end, "notes": "requested"}
        params = {"calendar_id": ID, "title": "Event", "start": START, "end": END, "notes": "requested"}
        for changes in ({"start": 0}, {"end": 1}, {"notes": "wrong"}, {"start": None}):
            with self.mock_run(payload(event={**event, **changes})):
                output = create_event(params)
            self.assertEqual(output["reason"], "readback_mismatch")
        with self.mock_run(payload(event=event)):
            self.assertEqual(create_event({**params, "start": "2026-11-05T18:00:00+08:00"})["status"], "verified")

    def test_unverified_build(self):
        with patch("ios_control_bridge.calendar.ios_version",
                   return_value={"ProductVersion": "17.0", "ProductBuildVersion": "other"}), \
             patch("ios_control_bridge.calendar.subprocess.run",
                   side_effect=AssertionError("unexpected helper")):
            output = list_calendars({})
        self.assertEqual(output["reason"], "unverified_os_build")


if __name__ == "__main__":
    unittest.main()
