import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge import siri
from ios_control_bridge.registry import invoke


def response(**changes):
    value = {"schema": siri.SCHEMA, "source": siri.SOURCE, "status": "verified", "language_code": "zh-CN"}
    value.update(changes)
    return subprocess.CompletedProcess([], {"verified": 0, "partial": 2, "error": 4}[value["status"]], json.dumps(value), "")


class SiriLanguageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.helper = Path(self.temp.name) / "helper"
        self.helper.touch()
        for target, value in (("helper_path", self.helper), ("ios_version", {"ProductVersion": "16.1.1", "ProductBuildVersion": "20B101"})):
            mocking = patch.object(siri, target, return_value=value)
            mocking.start()
            self.addCleanup(mocking.stop)

    def test_get_reads_effective_language(self):
        with patch.object(siri.subprocess, "run", return_value=response()):
            result = invoke("siri.language.get", {})
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["data"]["language_code"], "zh-CN")

    def test_set_requires_matching_independent_process_readback(self):
        first = response(before="en-US", requested="zh-CN", readback="zh-CN")
        with patch.object(siri.subprocess, "run", side_effect=[first, response()]) as run:
            result = invoke("siri.language.set", {"language_code": "zh-CN"})
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["data"]["independent_readback"], "zh-CN")
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0][-2:], ["set-language", "zh-CN"])
        self.assertEqual(run.call_args_list[1].args[0][-1:], ["get"])

    def test_bad_or_unknown_parameters_never_launch_helper(self):
        with patch.object(siri.subprocess, "run", side_effect=AssertionError("unexpected helper")):
            for params in ({"language_code": "zh-CN; reboot"}, {"language_code": True}, {}, {"language_code": "zh-CN", "extra": 1}):
                self.assertEqual(invoke("siri.language.set", params)["status"], "error")

    def test_supported_build_gate_precedes_helper(self):
        with patch.object(siri, "ios_version", return_value={"ProductVersion": "18.0", "ProductBuildVersion": "other"}), \
             patch.object(siri.subprocess, "run", side_effect=AssertionError("unexpected helper")):
            self.assertEqual(invoke("siri.language.get", {})["reason"], "unverified_os_build")

    def test_exit_or_source_mismatch_is_not_success(self):
        for malformed in (subprocess.CompletedProcess([], 4, response().stdout, ""), response(source="other")):
            with patch.object(siri.subprocess, "run", return_value=malformed):
                self.assertEqual(invoke("siri.language.get", {})["status"], "unavailable")

    def test_stale_readback_cannot_confirm_write(self):
        with patch.object(siri.subprocess, "run", side_effect=[response(before="en-US", requested="zh-CN", readback="zh-CN"), response(language_code="en-US")]):
            self.assertEqual(invoke("siri.language.set", {"language_code": "zh-CN"})["reason"], "independent_readback_failed")

    def test_mismatched_native_write_does_not_launch_second_get(self):
        with patch.object(siri.subprocess, "run", return_value=response(before="en-US", requested="zh-CN", readback="en-US")) as run:
            self.assertEqual(invoke("siri.language.set", {"language_code": "zh-CN"})["status"], "partial")
            self.assertEqual(run.call_count, 1)

    def test_timeout_reports_unconfirmed_operation(self):
        with patch.object(siri.subprocess, "run", side_effect=subprocess.TimeoutExpired("helper", 8)):
            self.assertEqual(invoke("siri.language.set", {"language_code": "zh-CN"})["reason"], "native_process_timeout")

    def test_delayed_preference_write_is_confirmed_only_by_fresh_process(self):
        pending = response(status="partial", reason="readback_mismatch", before="en-US", requested="zh-CN", readback="en-US", language_code="en-US")
        with patch.object(siri.subprocess, "run", side_effect=[pending, response(language_code="en-US"), response()]) as run, patch.object(siri.time, "sleep"):
            result = invoke("siri.language.set", {"language_code": "zh-CN"})
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["data"]["native_cached_readback"], "en-US")
        self.assertEqual(result["data"]["independent_readback"], "zh-CN")
        self.assertEqual(sum(call.args[0][-2:] == ["set-language", "zh-CN"] for call in run.call_args_list), 1)


if __name__ == "__main__":
    unittest.main()
