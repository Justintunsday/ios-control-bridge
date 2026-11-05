from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge.files import list_files, read_file, search_files


class FilesBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "alpha.txt").write_bytes(b"hello world\n")
        (self.root / "beta.log").write_text("log\n", encoding="utf8")
        (self.root / ".hidden").write_text("hidden\n", encoding="utf8")
        (self.root / "sub").mkdir()
        (self.root / "sub" / "gamma.txt").write_text("gamma\n", encoding="utf8")
        self.addCleanup(self.temp.cleanup)

    def test_list_is_sorted_and_hides_dotfiles(self):
        output = list_files({"path": str(self.root)})
        self.assertEqual(output["status"], "verified")
        names = [entry["name"] for entry in output["data"]["entries"]]
        self.assertEqual(names, ["sub", "alpha.txt", "beta.log"])

    def test_list_limit_and_hidden_option(self):
        output = list_files({"path": str(self.root), "limit": 2, "include_hidden": True})
        self.assertEqual(output["status"], "verified")
        self.assertTrue(output["data"]["truncated"])
        self.assertIn(".hidden", [entry["name"] for entry in output["data"]["entries"]])

    def test_list_rejects_relative_path_and_bad_limit(self):
        self.assertEqual(list_files({"path": "relative"})["reason"], "invalid_path")
        self.assertEqual(list_files({"path": str(self.root), "limit": 0})["reason"], "invalid_limit")

    def test_list_missing_directory(self):
        output = list_files({"path": str(self.root / "missing")})
        self.assertEqual(output["status"], "unavailable")
        self.assertEqual(output["reason"], "path_not_found")

    def test_search_is_bounded(self):
        output = search_files({"path": str(self.root), "query": "a", "limit": 1, "max_depth": 2})
        self.assertEqual(output["status"], "verified")
        self.assertEqual(output["data"]["count"], 1)
        self.assertTrue(output["data"]["truncated"])

    def test_search_into_subdirectory(self):
        output = search_files({"path": str(self.root), "query": "gamma", "max_depth": 2})
        self.assertEqual(output["status"], "verified")
        self.assertEqual([item["name"] for item in output["data"]["matches"]], ["gamma.txt"])
        self.assertEqual(output["data"]["matches"][0]["relative_path"], str(Path("sub") / "gamma.txt"))

    def test_search_root_permission_error_is_not_empty_success(self):
        with patch("ios_control_bridge.files.os.scandir", side_effect=PermissionError()):
            output = search_files({"path": str(self.root), "query": "anything"})
        self.assertEqual(output["status"], "unavailable")
        self.assertEqual(output["reason"], "permission_denied")
        self.assertFalse(output["complete_for_scope"])

    def test_search_child_permission_error_retains_readable_matches(self):
        original = os.scandir
        def scan(path):
            if Path(path).name == "sub":
                raise PermissionError()
            return original(path)
        with patch("ios_control_bridge.files.os.scandir", side_effect=scan):
            output = search_files({"path": str(self.root), "query": "alpha"})
        self.assertEqual(output["status"], "partial")
        self.assertEqual(output["data"]["matches"][0]["relative_path"], "alpha.txt")
        self.assertEqual(output["data"]["failed_directories"], 1)

    def test_same_name_in_two_directories_has_distinct_locations(self):
        (self.root / "sub" / "alpha.txt").write_text("second", encoding="utf8")
        output = search_files({"path": str(self.root), "query": "alpha"})
        locations = {row["relative_path"] for row in output["data"]["matches"]}
        self.assertEqual(locations, {"alpha.txt", str(Path("sub") / "alpha.txt")})

    def test_read_returns_content(self):
        output = read_file({"path": str(self.root / "alpha.txt")})
        self.assertEqual(output["status"], "verified")
        self.assertEqual(output["data"]["content"], "hello world\n")
        self.assertFalse(output["data"]["truncated"])

    def test_read_truncates_by_max_bytes(self):
        output = read_file({"path": str(self.root / "alpha.txt"), "max_bytes": 5})
        self.assertEqual(output["status"], "partial")
        self.assertTrue(output["data"]["truncated"])
        self.assertEqual(output["data"]["bytes_read"], 5)

    def test_read_rejects_binary_and_missing(self):
        binary = self.root / "binary.bin"
        binary.write_bytes(b"\x00\x01\x02")
        self.assertEqual(read_file({"path": str(binary)})["reason"], "binary_file")
        self.assertEqual(read_file({"path": str(self.root / "missing")})["reason"], "path_not_found")


if __name__ == "__main__":
    unittest.main()
