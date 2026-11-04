#!/usr/bin/env python3
"""Offline contract tests with synthetic command fixtures; no SSH/device access.

Run: python test_probe.py --shell /path/to/sh-or-bash
Only the temporary fixture directory is written. Python 3.10+, POSIX shell,
and its usual tr/awk/date commands are needed.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PROBE = Path(__file__).with_name("probe_ios.sh")
SHELL = None


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ios-skill-fixture-")
        self.root = Path(self.temp.name)
        self.bin = self.root / "fixture-bootstrap" / "usr" / "bin"
        self.bin.mkdir(parents=True)
        self.forbidden = self.root / "unexpected-command.txt"
        self.env = dict(os.environ)
        self.env.pop("BASH_ENV", None)
        self.env.pop("ENV", None)
        self.env["PATH"] = str(self.bin) + os.pathsep + self.env.get("PATH", "")
        self.env["IOS_PROBE_TEST_FORBIDDEN"] = str(self.forbidden).replace("\\", "/")
        self.stub("uname", '''
case "$1" in
    -s) printf '%s\\n' "${IOS_PROBE_TEST_KERNEL:-Darwin}" ;;
    -r) printf '%s\\n' '22.1.0' ;;
    *) exit 64 ;;
esac
''')
        self.stub("sysctl", '''
if [ "${IOS_PROBE_TEST_SYSCTL_FAIL:-0}" = 1 ]; then exit 7; fi
printf '%s\\n' "${IOS_PROBE_TEST_MACHINE:-iPhone12,8}"
''')
        self.stub("id", '''
case "$1" in
    -u) printf '%s\\n' "${IOS_PROBE_TEST_UID:-501}" ;;
    -un) printf '%s\\n' 'mobile' ;;
    *) exit 64 ;;
esac
''')
        self.stub("plutil", '''
if [ "${IOS_PROBE_TEST_PLUTIL_FAIL:-0}" = 1 ]; then exit 64; fi
printf '%s\\n' '16.1.1'
''')
        self.stub("sw_vers", '''
if [ "${IOS_PROBE_TEST_SW_FAIL:-0}" = 1 ]; then exit 64; fi
printf '%s\\n' '16.2'
''')
        self.stub("dpkg", '''
if [ "$1" != --print-architecture ]; then
    printf '%s\\n' 'dpkg write attempt' >> "$IOS_PROBE_TEST_FORBIDDEN"
    exit 97
fi
if [ "${IOS_PROBE_TEST_DPKG_FAIL:-0}" = 1 ]; then exit 7; fi
printf '%s\\n' 'iphoneos-arm64'
''')
        self.stub("uptime", "printf '%s\\n' '12:00 up 1 day, load averages: 0.1 0.2 0.3'\n")
        self.stub("df", '''
if [ "${IOS_PROBE_TEST_DF_FAIL:-0}" = 1 ]; then
    printf '%s\\n' 'Permission denied: /var/mobile' >&2
    exit 7
fi
printf '%s\\n' 'Filesystem 1024-blocks Used Available Capacity Mounted on' '/dev/disk 1000 200 800 20% /'
''')
        self.stub("vm_stat", '''
probe_test_n=0
while [ "$probe_test_n" -lt "${IOS_PROBE_TEST_VM_LINES:-2}" ]; do
    printf 'Pages free: %s\\n' "$probe_test_n"
    probe_test_n=$((probe_test_n + 1))
done
''')
        self.stub("ioreg", '''
case "${IOS_PROBE_TEST_BATTERY:-normal}" in
    fail) exit 78 ;;
    empty) printf '%s\\n' 'No matching properties'; exit 0 ;;
esac
printf '%s\\n' ' | "CurrentCapacity" = 57' ' | "MaxCapacity" = 100' ' | "IsCharging" = Yes' ' | "Temperature" = 3010' ' | "SerialNumber" = "DO-NOT-LEAK"' ' | "BatteryData" = {"CurrentCapacity" = 999, "SerialNumber" = "NESTED-SECRET"}'
''')
        for name in ("sudo", "su", "apt", "apt-get", "mount", "kill", "launchctl", "ssh", "scp", "curl"):
            self.stub(name, '''
printf '%s\\n' "$0 $*" >> "$IOS_PROBE_TEST_FORBIDDEN"
exit 97
''')

    def tearDown(self):
        try:
            self.assertFalse(self.forbidden.exists(), "Probe executed an unexpected command")
        finally:
            self.temp.cleanup()

    def stub(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8", newline="\n")
        path.chmod(0o700)

    def run_probe(self, *args, **config):
        env = dict(self.env)
        env.update({"IOS_PROBE_TEST_" + k: str(v) for k, v in config.items()})
        # Git Bash prepends its own /usr/bin at native process startup. Set
        # fixture priority inside the shell, without interpolating data into
        # shell code. Source after shifting so the probe receives only args.
        wrapper = '''
probe_test_bin=$(cd "$1" && pwd -P) || exit 90
probe_test_script=$2
PATH="$probe_test_bin:$PATH"
export PATH
shift 2
. "$probe_test_script"
'''
        result = subprocess.run(
            [SHELL, "-c", wrapper, "ios-probe-fixture", self.bin.as_posix(), PROBE.as_posix(), *args],
            env=env, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=15,
        )
        fields = {}
        for line in result.stdout.splitlines():
            if "\t" in line:
                key, value = line.split("\t", 1)
                fields[key] = value
        return result, fields

    def test_non_darwin_is_not_a_phone(self):
        result, fields = self.run_probe(KERNEL="Linux")
        self.assertEqual(result.returncode, 4)
        self.assertEqual(fields["result.status"], "unavailable")
        self.assertNotIn("user.uid", fields)
        self.assertNotIn("disk.line", fields)

    def test_mac_is_not_an_iphone(self):
        result, fields = self.run_probe("status", MACHINE="Mac14,2")
        self.assertEqual(result.returncode, 4)
        self.assertNotIn("ios.version", fields)
        self.assertNotIn("disk.line", fields)

    def test_unverified_hardware_stops(self):
        result, fields = self.run_probe(SYSCTL_FAIL=1)
        self.assertEqual(result.returncode, 4)
        self.assertEqual(fields["device.hardware"], "unknown")

    def test_ios_16_1_environment(self):
        result, fields = self.run_probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(fields["ios.version"], "16.1.1")
        self.assertEqual(fields["ios.version_source"], "SystemVersion.plist")
        self.assertEqual(fields["user.uid"], "501")
        self.assertEqual(fields["packages.architecture"], "iphoneos-arm64")
        self.assertEqual(fields["result.status"], "verified")
        self.assertEqual(fields["live_activities.source"], "not_probed")

    def test_root_uid_does_not_override_custom_prefix(self):
        result, fields = self.run_probe(UID=0, MACHINE="iPad13,4")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(fields["user.uid"], "0")
        self.assertNotEqual(fields["bootstrap.scheme_evidence"], "rootful_candidate")
        self.assertIn("fixture-bootstrap", fields["bootstrap.tool_prefix_candidate"])

    def test_version_falls_back_to_sw_vers(self):
        result, fields = self.run_probe(PLUTIL_FAIL=1)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(fields["ios.version"], "16.2")
        self.assertEqual(fields["ios.version_source"], "sw_vers")

    def test_missing_version_is_unknown_not_latest(self):
        result, fields = self.run_probe(PLUTIL_FAIL=1, SW_FAIL=1)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(fields["ios.version"], "unknown")
        self.assertEqual(fields["result.status"], "partial")

    def test_architecture_failure_is_reported(self):
        _, fields = self.run_probe(DPKG_FAIL=1)
        self.assertEqual(fields["packages.architecture"], "unknown")
        self.assertEqual(fields["result.status"], "partial")

    def test_battery_whitelist_excludes_identifiers_and_nested_data(self):
        result, fields = self.run_probe("status")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(fields["battery.status"], "verified")
        self.assertIn('"CurrentCapacity" = 57', result.stdout)
        self.assertIn('"Temperature" = 3010', result.stdout)
        self.assertNotIn("SerialNumber", result.stdout)
        self.assertNotIn("DO-NOT-LEAK", result.stdout)
        self.assertNotIn("NESTED-SECRET", result.stdout)
        self.assertNotIn("999", result.stdout)

    def test_no_battery_fields_does_not_mean_zero_percent(self):
        result, fields = self.run_probe("status", BATTERY="empty")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(fields["battery.status"], "unavailable")
        self.assertNotIn("battery.raw", fields)
        self.assertEqual(fields["result.status"], "partial")

    def test_disk_permission_error_is_preserved(self):
        result, fields = self.run_probe("status", DF_FAIL=1)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(fields["disk.status"], "error")
        self.assertEqual(fields["disk.exit_code"], "7")
        self.assertIn("Permission denied", result.stdout)
        self.assertEqual(fields["result.status"], "partial")

    def test_battery_error_is_distinct_from_empty_data(self):
        _, fields = self.run_probe("status", BATTERY="fail")
        self.assertEqual(fields["battery.status"], "error")
        self.assertEqual(fields["battery.exit_code"], "78")
        self.assertEqual(fields["result.status"], "partial")

    def test_untrusted_argument_is_not_executed(self):
        marker = self.root / "argument-executed"
        payload = "$(touch '" + marker.as_posix() + "')"
        result, fields = self.run_probe(payload)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(marker.exists())
        self.assertEqual(fields, {})

    def test_extra_arguments_are_rejected(self):
        result, fields = self.run_probe("status", "extra")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(fields, {})

    def test_truncated_status_output_is_partial(self):
        result, fields = self.run_probe("status", VM_LINES=100)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(fields["memory.truncated"], "true")
        self.assertEqual(result.stdout.count("memory.line\t"), 80)
        self.assertEqual(fields["result.status"], "partial")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shell", help="POSIX sh/bash executable")
    options, remaining = parser.parse_known_args()
    SHELL = options.shell or shutil.which("sh") or shutil.which("bash")
    if not SHELL:
        parser.error("Provide an existing POSIX shell with --shell")
    unittest.main(argv=[__file__, *remaining])
