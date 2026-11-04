from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge.activities import get_activity, NATIVE_SCHEMA, NATIVE_SOURCE

ID = "1DF0A9B7-6211-4FD8-A80A-03BEF357532A"
OTHER_ID = "52B50427-9417-4C7C-A8FC-7A6904E93872"


class NativeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.binary = Path(self.temp.name) / "icb-activities"
        self.binary.touch()
        self.version = patch("ios_control_bridge.activities.ios_version", return_value={
            "ProductVersion": "16.1.1", "ProductBuildVersion": "20B101"})
        self.helper = patch("ios_control_bridge.activities.helper_path", return_value=self.binary)
        self.version.start(); self.helper.start()
        self.addCleanup(self.version.stop); self.addCleanup(self.helper.stop); self.addCleanup(self.temp.cleanup)

    def payload(self, **changes):
        value = {"schema": NATIVE_SCHEMA, "source": NATIVE_SOURCE, "status": "verified",
                 "requested_activity_id": ID, "complete_for_scope": True,
                 "target_found": False, "activity": None, "observed_at": "2026-01-01T00:00:00Z"}
        value.update(changes)
        return value

    def query(self, payload, exit_code=0):
        process = subprocess.CompletedProcess([], exit_code, json.dumps(payload), "")
        with patch("ios_control_bridge.activities.subprocess.run", return_value=process) as call:
            output = get_activity({"activity_id": ID})
        self.assertEqual(call.call_args.args[0][1:3], ["--activity-id", ID])
        self.assertNotIn("shell", call.call_args.kwargs)
        return output

    def test_completed_empty_response_is_not_failure(self):
        output = self.query(self.payload())
        self.assertEqual(output["status"], "verified")
        self.assertTrue(output["complete_for_scope"])
        self.assertIsNone(output["data"]["activity"])

    def test_real_content_is_preserved_without_reinterpreting_fields(self):
        output = self.query(self.payload(target_found=True, activity={"state": {"active": {}}, "descriptor": {"id": ID}},
                                         content={"value": 47, "updatedAt": 123.5}))
        self.assertEqual(output["data"]["content"], {"value": 47, "updatedAt": 123.5})

    def test_missing_target_cannot_include_stale_content(self):
        output = self.query(self.payload(content={"value": 47}))
        self.assertEqual(output["reason"], "native_activity_inconsistent")
        self.assertNotIn("data", output)

    def test_body_descriptor_must_match_the_requested_target(self):
        output = self.query(self.payload(target_found=True, activity={"descriptor": {"id": OTHER_ID}}, content={"value": 47}))
        self.assertEqual(output["reason"], "native_activity_inconsistent")

    def test_wrong_target_is_rejected(self):
        output = self.query(self.payload(requested_activity_id=OTHER_ID))
        self.assertEqual(output["reason"], "native_target_mismatch")
        self.assertNotIn("data", output)

    def test_native_exit_and_status_must_agree(self):
        output = self.query(self.payload(), exit_code=3)
        self.assertEqual(output["reason"], "native_exit_status_mismatch")

    def test_claimed_success_requires_complete_response(self):
        output = self.query(self.payload(complete_for_scope=False))
        self.assertEqual(output["reason"], "incomplete_native_success")

    def test_process_timeout_has_no_old_content(self):
        with patch("ios_control_bridge.activities.subprocess.run", side_effect=subprocess.TimeoutExpired([], 1)):
            output = get_activity({"activity_id": ID})
        self.assertEqual(output["status"], "unavailable")
        self.assertEqual(output["reason"], "native_process_timeout")
        self.assertNotIn("data", output)

    def test_metacharacters_never_reach_a_subprocess(self):
        with patch("ios_control_bridge.activities.subprocess.run", side_effect=AssertionError("unexpected command")):
            output = get_activity({"activity_id": "$(touch /tmp/unwanted); '"})
        self.assertEqual(output["reason"], "invalid_activity_id")

    def test_unverified_system_does_not_start_helper(self):
        with patch("ios_control_bridge.activities.ios_version", return_value={"ProductVersion": "17.0", "ProductBuildVersion": "other"}), \
             patch("ios_control_bridge.activities.subprocess.run", side_effect=AssertionError("unexpected helper")):
            output = get_activity({"activity_id": ID})
        self.assertEqual(output["reason"], "unverified_os_build")


if __name__ == "__main__":
    unittest.main()
