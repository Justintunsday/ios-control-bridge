"""Run the corrected regressions for the 2026-11-05 review.

The original failing reproduction is preserved in commit 99befe7.
Native control-flow cases run separately with tools/test_native.py on device.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
CASES = [
    "test_watch.WatchBoundaryTests.test_body_change_while_active_is_detected_and_preserved",
    "test_files.FilesBoundaryTests.test_search_root_permission_error_is_not_empty_success",
    "test_ellekit.ElleKitBridgeTests.test_timeout_after_write_is_unknown_and_is_not_retried",
    "test_ellekit.ElleKitBridgeTests.test_no_persistent_command_or_aliased_file_is_written",
    "test_ellekit.ElleKitBridgeTests.test_concurrent_clients_have_independent_responses",
    "test_calendar.CalendarBoundaryTests.test_create_rejects_old_identity_or_wrong_source",
    "test_calendar.CalendarBoundaryTests.test_event_time_and_notes_must_match_readback",
    "test_files.FilesBoundaryTests.test_same_name_in_two_directories_has_distinct_locations",
]
if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromNames(CASES)
    outcome = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if outcome.wasSuccessful() else 1)
