from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge.settings import NATIVE_SCHEMA, NATIVE_SOURCE, get_setting, set_setting

VERSION = {"ProductVersion": "16.1.1", "ProductBuildVersion": "20B101"}


class SettingsBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.binary = Path(self.temp.name) / "icb-settings"
        self.binary.touch()
        self.version = patch("ios_control_bridge.settings.ios_version", return_value=VERSION)
        self.helper = patch("ios_control_bridge.settings.helper_path", return_value=self.binary)
        self.version.start()
        self.helper.start()
        self.addCleanup(self.version.stop)
        self.addCleanup(self.helper.stop)
        self.addCleanup(self.temp.cleanup)

    def payload(self, **changes):
        value = {
            "schema": NATIVE_SCHEMA,
            "status": "verified",
            "setting": "volume",
            "category": "Audio/Video",
            "source": NATIVE_SOURCE,
            "observed_at_unix": 1.0,
            "value": 0.5,
        }
        value.update(changes)
        return value

    def set_payload(self, **changes):
        value = self.payload(before=0.0, requested=0.5, readback=0.5, delta=0.0,
                             tolerance=0.001, verified=True)
        value.update(changes)
        return value

    def query(self, helper_payload, exit_code=0, params=None):
        process = subprocess.CompletedProcess([], exit_code, json.dumps(helper_payload), "")
        with patch("ios_control_bridge.settings.subprocess.run", return_value=process) as call:
            output = get_setting(params or {"setting": "volume"})
        self.assertEqual(call.call_args.args[0][1:], ["get", "volume"])
        return output

    def set_value(self, helper_payload, exit_code=0, params=None):
        process = subprocess.CompletedProcess([], exit_code, json.dumps(helper_payload), "")
        with patch("ios_control_bridge.settings.subprocess.run", return_value=process) as call:
            output = set_setting(params or {"setting": "volume", "value": 0.5})
        self.assertEqual(call.call_args.args[0][1:], ["set", "volume", "0.500000000"])
        return output

    def test_get_volume_returns_device_value(self):
        output = self.query(self.payload())
        self.assertEqual(output["status"], "verified")
        self.assertEqual(output["data"]["value"], 0.5)
        self.assertTrue(output["complete_for_scope"])
        self.assertEqual(output["source"], NATIVE_SOURCE)

    def test_unsupported_setting_does_not_start_helper(self):
        with patch("ios_control_bridge.settings.subprocess.run",
                   side_effect=AssertionError("unexpected helper")):
            output = get_setting({"setting": "brightness"})
        self.assertEqual(output["status"], "unavailable")
        self.assertEqual(output["reason"], "unsupported_setting")
        self.assertEqual(output["data"]["supported_settings"], ["volume"])

    def test_unknown_parameters_are_rejected_before_helper(self):
        with patch("ios_control_bridge.settings.subprocess.run",
                   side_effect=AssertionError("unexpected helper")):
            output = get_setting({"setting": "volume", "extra": True})
        self.assertEqual(output["reason"], "unknown_parameters")

    def test_missing_value_is_rejected(self):
        output = set_setting({"setting": "volume"})
        self.assertEqual(output["reason"], "missing_value")

    def test_value_must_be_a_finite_number_in_range(self):
        for value in (True, "0.5", -0.01, 1.01, float("nan"), float("inf")):
            output = set_setting({"setting": "volume", "value": value})
            self.assertEqual(output["reason"], "invalid_value", repr(value))

    def test_set_readback_confirms_value(self):
        output = self.set_value(self.set_payload())
        self.assertEqual(output["status"], "verified")
        self.assertTrue(output["complete_for_scope"])
        self.assertEqual(output["data"]["readback"], 0.5)

    def test_set_partial_readback_is_not_verified(self):
        output = self.set_value(self.set_payload(status="partial", readback=0.4, delta=-0.1,
                                                 verified=False, reason="readback_mismatch"), exit_code=2)
        self.assertEqual(output["status"], "partial")
        self.assertFalse(output["complete_for_scope"])
        self.assertEqual(output["reason"], "readback_mismatch")

    def test_helper_verified_with_mismatched_readback_is_not_trusted(self):
        output = self.set_value(self.set_payload(readback=0.4, delta=-0.1))
        self.assertEqual(output["status"], "partial")
        self.assertEqual(output["reason"], "readback_mismatch")

    def test_native_exit_and_status_must_agree(self):
        output = self.query(self.payload(), exit_code=3)
        self.assertEqual(output["reason"], "native_exit_status_mismatch")

    def test_native_source_is_checked(self):
        output = self.query(self.payload(source="unknown"))
        self.assertEqual(output["reason"], "native_source_mismatch")

    def test_unverified_build_does_not_start_helper(self):
        with patch("ios_control_bridge.settings.ios_version",
                   return_value={"ProductVersion": "17.0", "ProductBuildVersion": "other"}), \
             patch("ios_control_bridge.settings.subprocess.run",
                   side_effect=AssertionError("unexpected helper")):
            output = get_setting({"setting": "volume"})
        self.assertEqual(output["reason"], "unverified_os_build")

    def test_timeout_returns_unavailable(self):
        with patch("ios_control_bridge.settings.subprocess.run",
                   side_effect=subprocess.TimeoutExpired([], 1)):
            output = get_setting({"setting": "volume"})
        self.assertEqual(output["status"], "unavailable")
        self.assertEqual(output["reason"], "native_process_timeout")


if __name__ == "__main__":
    unittest.main()
