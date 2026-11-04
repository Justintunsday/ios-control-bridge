from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge.device import device_info, ios_version


class DeviceIdentityTests(unittest.TestCase):
    def test_macos_plist_is_not_an_ios_device(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "SystemVersion.plist"
            file.write_bytes(plistlib.dumps({"ProductName": "macOS", "ProductVersion": "26.0"}))
            with patch("ios_control_bridge.device.sys.platform", "darwin"):
                self.assertIsNone(ios_version(file))

    def test_missing_model_is_partial_and_explicit(self):
        with patch("ios_control_bridge.device.ios_version", return_value={"ProductName": "iPhone OS", "ProductVersion": "16.1.1"}), \
             patch("ios_control_bridge.device.os.geteuid", create=True, return_value=0), \
             patch("ios_control_bridge.device.shutil.which", return_value=None), \
             patch("ios_control_bridge.device.os.path.exists", return_value=False):
            output = device_info()
        self.assertEqual(output["status"], "partial")
        self.assertIsNone(output["data"]["model"])
        self.assertFalse(output["complete_for_scope"])


if __name__ == "__main__":
    unittest.main()
