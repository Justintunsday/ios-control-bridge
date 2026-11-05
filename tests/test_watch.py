from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge.activities import NATIVE_SCHEMA, NATIVE_SOURCE, watch_activity

ID = "1DF0A9B7-6211-4FD8-A80A-03BEF357532A"


class WatchBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.binary = Path(self.temp.name) / "icb-activities"
        self.binary.touch()
        self.version = patch("ios_control_bridge.activities.ios_version", return_value={
            "ProductVersion": "16.1.1", "ProductBuildVersion": "20B101"})
        self.helper = patch("ios_control_bridge.activities.helper_path", return_value=self.binary)
        self.version.start()
        self.helper.start()
        self.addCleanup(self.version.stop)
        self.addCleanup(self.helper.stop)
        self.addCleanup(self.temp.cleanup)

    def probe(self, target_found=False, state=None, status="verified", content=None):
        activity = None
        if target_found:
            activity = {"descriptor": {"id": ID}, "state": state or {"active": {}}}
        return {"status": status, "observed_at": "2026-01-01T00:00:00Z",
                "request_id": "00000000-0000-0000-0000-000000000000",
                "data": {"schema": NATIVE_SCHEMA, "source": NATIVE_SOURCE,
                         "target_found": target_found, "activity": activity, "content": content}}

    def test_validation(self):
        self.assertEqual(watch_activity({})["reason"], "invalid_activity_id")
        self.assertEqual(watch_activity({"activity_id": ID, "duration_ms": 0})["reason"], "invalid_duration_ms")
        self.assertEqual(watch_activity({"activity_id": ID, "interval_ms": 100})["reason"], "invalid_interval_ms")
        self.assertEqual(watch_activity({"activity_id": ID, "timeout_ms": 10})["reason"], "invalid_timeout_ms")
        self.assertEqual(watch_activity({"activity_id": ID, "stop_on_change": 1})["reason"],
                         "invalid_stop_on_change")

    def test_missing_activity_collects_samples(self):
        samples = [self.probe() for _ in range(4)]
        with patch("ios_control_bridge.activities.get_activity", side_effect=samples), \
             patch("ios_control_bridge.activities.time.monotonic", side_effect=[0, 0, 2]), \
             patch("ios_control_bridge.activities.time.sleep"):
            output = watch_activity({"activity_id": ID, "duration_ms": 1000, "interval_ms": 500})
        self.assertEqual(output["status"], "verified")
        self.assertEqual(len(output["data"]["samples"]), 2)
        self.assertFalse(output["data"]["target_found_ever"])
        self.assertFalse(output["data"]["changed"])

    def test_stop_on_change(self):
        samples = [self.probe(True, {"active": {"value": 1}}), self.probe(True, {"active": {"value": 2}})]
        with patch("ios_control_bridge.activities.get_activity", side_effect=samples), \
             patch("ios_control_bridge.activities.time.monotonic", side_effect=[0, 0, 2]), \
             patch("ios_control_bridge.activities.time.sleep"):
            output = watch_activity({"activity_id": ID, "duration_ms": 2000,
                                     "interval_ms": 500, "stop_on_change": True})
        self.assertEqual(output["status"], "verified")
        self.assertTrue(output["data"]["stopped_early"])
        self.assertTrue(output["data"]["changed"])
        self.assertFalse(output["complete_for_scope"])

    def test_rejected_probe_is_reported(self):
        with patch("ios_control_bridge.activities.get_activity", return_value={
                "status": "unavailable", "reason": "native_process_timeout", "request_id": "x"}):
            output = watch_activity({"activity_id": ID, "duration_ms": 1000})
        self.assertEqual(output["status"], "unavailable")
        self.assertEqual(output["reason"], "native_process_timeout")

    def run_samples(self, probes):
        with patch("ios_control_bridge.activities.get_activity", side_effect=probes), \
             patch("ios_control_bridge.activities.time.monotonic", side_effect=[0, 0, 2]), \
             patch("ios_control_bridge.activities.time.sleep"):
            return watch_activity({"activity_id": ID, "duration_ms": 1000, "stop_on_change": True})

    def test_body_change_while_active_is_detected_and_preserved(self):
        output = self.run_samples([self.probe(True, content={"value": 10}),
                                   self.probe(True, content={"value": 20})])
        self.assertTrue(output["data"]["changed"])
        self.assertTrue(output["data"]["stopped_early"])
        self.assertEqual(output["data"]["samples"][-1]["content"], {"value": 20})

    def test_appearance_and_disappearance_are_changes(self):
        for samples in ([self.probe(), self.probe(True, content={})],
                        [self.probe(True, content={}), self.probe()]):
            self.assertTrue(self.run_samples(samples)["data"]["changed"])

    def test_equal_body_with_different_json_key_order_is_not_change(self):
        output = self.run_samples([self.probe(True, content={"a": 1, "b": 2}),
                                   self.probe(True, content={"b": 2, "a": 1})])
        self.assertFalse(output["data"]["changed"])


if __name__ == "__main__":
    unittest.main()
