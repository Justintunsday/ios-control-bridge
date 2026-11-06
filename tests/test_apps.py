import io
import errno
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge import apps
from ios_control_bridge.registry import invoke

BUNDLE = "dev.ioscontrol.appsfixture"


def state(installed=False, version="1", placeholder=False, protected=False):
    return {"status": "verified", "app": {"bundle_id": BUNDLE, "installed": installed,
            "version": version, "placeholder": placeholder, "protected": protected}}


def ipa(path, **changes):
    info = {"CFBundleIdentifier": BUNDLE, "CFBundleVersion": "1", "CFBundleExecutable": "Fixture"}
    info.update(changes)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Payload/Fixture.app/Info.plist", plistlib.dumps(info))
        archive.writestr("Payload/Fixture.app/Fixture", b"fixture")


class AppsTests(unittest.TestCase):
    def setUp(self):
        self.ready = patch.object(apps, "readiness", return_value=(True, None))
        self.ready.start()
        self.addCleanup(self.ready.stop)

    def test_exact_id_and_known_parameters_are_required(self):
        with patch.object(apps, "_native") as native:
            for operation, params in [
                ("apps.uninstall", {"bundle_id": "Twitter"}),
                ("apps.uninstall", {"bundle_id": "com.example.*"}),
                ("apps.uninstall", {"bundle_id": BUNDLE, "force": True}),
                ("apps.download", {"source": "ipa", "url": "http://example.com/app.ipa"}),
                ("apps.download", {"source": "ipa", "url": "https://name:secret@example.com/app.ipa"}),
                ("apps.download", {"source": "app_store", "url": "https://evil.example/id123"}),
                ("apps.install", {"path": "relative.ipa"}),
                ("apps.list", {"limit": True}),
            ]:
                self.assertEqual(invoke(operation, params)["status"], "error", (operation, params))
            native.assert_not_called()

    def test_uninstall_requires_independent_absence_and_no_placeholder(self):
        for after in (state(True), state(False, placeholder=True)):
            with patch.object(apps, "_get", side_effect=[state(True), after]), \
                 patch.object(apps, "_native", return_value={"status": "partial", "accepted": True}) as native:
                result = invoke("apps.uninstall", {"bundle_id": BUNDLE, "verify_timeout_ms": 0})
            self.assertEqual(result["status"], "partial")
            self.assertEqual(native.call_count, 1)

    def test_uninstall_verified_and_idempotent_absent(self):
        with patch.object(apps, "_get", side_effect=[state(True), state()]), \
             patch.object(apps, "_native", return_value={"status": "partial", "accepted": True}):
            result = invoke("apps.uninstall", {"bundle_id": BUNDLE, "verify_timeout_ms": 0}, "request-1")
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["request_id"], "request-1")
        with patch.object(apps, "_get", return_value=state()), patch.object(apps, "_native") as native:
            result = invoke("apps.uninstall", {"bundle_id": BUNDLE})
        self.assertFalse(result["data"]["changed"])
        native.assert_not_called()

    def test_protected_apps_and_unknown_preflight_never_mutate(self):
        for before in (state(True, protected=True), {"status": "unavailable", "reason": "read_failed"}):
            with patch.object(apps, "_get", return_value=before), patch.object(apps, "_native") as native:
                result = invoke("apps.uninstall", {"bundle_id": BUNDLE})
            self.assertNotEqual(result["status"], "verified")
            native.assert_not_called()

    def test_timeout_is_observed_once_and_never_replayed(self):
        with patch.object(apps, "_get", side_effect=[state(True), state(True)]), \
             patch.object(apps, "_native", return_value={"status": "partial", "outcome_unknown": True}) as native:
            self.assertEqual(invoke("apps.uninstall", {"bundle_id": BUNDLE, "verify_timeout_ms": 0})["status"], "partial")
        self.assertEqual(native.call_count, 1)

    def test_ipa_original_preserved_even_when_installer_consumes_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "app.ipa"
            ipa(source)
            original = source.read_bytes()
            def consume(command, params, **kwargs):
                self.assertEqual(command, "install")
                disposable = Path(params["path"])
                self.assertNotEqual(disposable, source)
                disposable.unlink()
                return {"status": "partial", "accepted": True}
            with patch.object(apps, "_get", side_effect=[state(), state(True)]), patch.object(apps, "_native", side_effect=consume):
                result = invoke("apps.install", {"path": str(source), "verify_timeout_ms": 0})
            self.assertEqual(result["status"], "verified")
            self.assertEqual(source.read_bytes(), original)

    def test_ipa_version_readback_must_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "app.ipa"
            ipa(source)
            with patch.object(apps, "_get", side_effect=[state(), state(True, version="2")]), \
                 patch.object(apps, "_native", return_value={"status": "partial", "accepted": True}):
                self.assertEqual(invoke("apps.install", {"path": str(source), "verify_timeout_ms": 0})["status"], "partial")

    def test_replace_must_be_explicit_and_checksum_must_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "app.ipa"
            ipa(source)
            for params, before in [({}, state(True)), ({"sha256": "0" * 64}, state()),
                                   ({"bundle_id": "dev.other.fixture"}, state())]:
                with patch.object(apps, "_get", return_value=before), patch.object(apps, "_native") as native:
                    result = invoke("apps.install", {"path": str(source), **params})
                self.assertEqual(result["status"], "error")
                native.assert_not_called()

    def test_malformed_ipa_and_unsafe_members_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "app.ipa"
            ipa(source)
            with zipfile.ZipFile(source, "a") as archive:
                archive.writestr("../escape", b"bad")
            with self.assertRaisesRegex(apps.AppError, "unsafe_ipa_member"):
                apps.inspect_ipa(source)
            source.write_bytes(b"not a zip")
            with self.assertRaisesRegex(apps.AppError, "invalid_ipa"):
                apps.inspect_ipa(source)

    def test_multiple_apps_and_escaping_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "app.ipa"
            ipa(source)
            with zipfile.ZipFile(source, "a") as archive:
                archive.writestr("Payload/Other.app/extra", b"bad")
            with self.assertRaisesRegex(apps.AppError, "invalid_ipa_manifest"):
                apps.inspect_ipa(source)
            ipa(source)
            with zipfile.ZipFile(source, "a") as archive:
                link = zipfile.ZipInfo("Payload/Fixture.app/escape")
                link.external_attr = 0o120777 << 16
                archive.writestr(link, "../../../escape")
            with self.assertRaisesRegex(apps.AppError, "unsafe_ipa_symlink"):
                apps.inspect_ipa(source)

    def test_installer_selection_is_explicit_and_never_falls_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "app.ipa"
            ipa(source)
            with patch.object(apps, "_get", return_value=state()), \
                 patch.object(apps, "_native", return_value={"status": "unavailable", "reason": "system_request_refused"}) as native:
                result = invoke("apps.install", {"path": str(source)})
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(native.call_count, 1)
            self.assertEqual(native.call_args.args[1]["installer"], "system")

    def test_symlinked_parent_cannot_hide_an_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "app.ipa"
            ipa(source)
            with zipfile.ZipFile(source, "a") as archive:
                for name, target in [("Payload/Fixture.app/parent", "."),
                                     ("Payload/Fixture.app/parent/escape", "../outside")]:
                    link = zipfile.ZipInfo(name)
                    link.external_attr = 0o120777 << 16
                    archive.writestr(link, target)
            with self.assertRaisesRegex(apps.AppError, "unsafe_ipa_symlink"):
                apps.inspect_ipa(source)

    def test_trollstore_deadline_allows_child_cleanup(self):
        with patch.object(apps, "_get", side_effect=[state(True), state()]), \
             patch.object(apps, "_native", return_value={"status": "partial", "accepted": True}) as native:
            result = invoke("apps.uninstall", {"bundle_id": BUNDLE, "installer": "trollstore", "verify_timeout_ms": 0})
        self.assertEqual(result["status"], "verified")
        self.assertEqual(native.call_args.kwargs["timeout"], 90)

    def test_paid_or_missing_offer_never_submits_store_download(self):
        with patch.object(apps, "_native", return_value={"status": "verified", "app": {"bundle_id": BUNDLE, "free_offer": False}}) as native:
            result = invoke("apps.download", {"source": "app_store", "app_id": "123"})
        self.assertEqual(result["reason"], "free_offer_required")
        self.assertEqual(native.call_count, 1)

    def test_app_store_url_resolves_and_download_requires_readback(self):
        info = {"status": "verified", "app": {"bundle_id": BUNDLE, "free_offer": True}}
        with patch.object(apps, "_get", side_effect=[state(), state(True)]), \
             patch.object(apps, "_native", side_effect=[info, {"status": "partial", "accepted": True}]) as native:
            result = invoke("apps.download", {"source": "app_store", "url": "https://apps.apple.com/hk/app/fixture/id123?l=en", "verify_timeout_ms": 0})
        self.assertEqual(result["status"], "verified")
        self.assertEqual(native.call_args_list[1].args, ("store_download", {"app_id": "123", "bundle_id": BUNDLE}))

    def test_existing_store_placeholder_is_not_purchased_again(self):
        info = {"status": "verified", "app": {"bundle_id": BUNDLE, "free_offer": True}}
        with patch.object(apps, "_get", return_value=state(True, placeholder=True)), \
             patch.object(apps, "_native", return_value=info) as native:
            result = invoke("apps.download", {"source": "app_store", "app_id": "123"})
        self.assertEqual(result["reason"], "store_download_pending")
        self.assertEqual(native.call_count, 1)

    def test_store_worker_returns_ack_without_terminating_authentication(self):
        payload = {"schema": apps.SCHEMA, "source": apps.SOURCE, "command": "store_download", "status": "partial",
                   "bundle_id": BUNDLE, "app_id": "123", "observed_at_unix": time.time(), "submitted": True,
                   "worker_pid": 222, "worker_expires_at_unix": time.time()+600}
        process = Mock(pid=222)
        process.poll.return_value = None
        def spawn(*args, **kwargs):
            kwargs["stdout"].write((json.dumps(payload)+"\n").encode())
            kwargs["stdout"].flush()
            self.assertTrue(kwargs["start_new_session"])
            self.assertEqual(len(kwargs["pass_fds"]), 1)
            return process
        with tempfile.TemporaryDirectory() as temporary:
            lease = os.open(str(Path(temporary)/"lease"), os.O_CREAT | os.O_RDWR, 0o600)
            with patch.object(apps, "_store_lease", return_value=lease), \
                 patch.object(apps, "_store_directory", return_value=Path(temporary)), \
                 patch.object(apps.os, "O_NOFOLLOW", 0, create=True), \
                 patch.object(apps.subprocess, "Popen", side_effect=spawn):
                value = apps._native("store_download", {"app_id": "123", "bundle_id": BUNDLE})
        self.assertEqual(value["status"], "partial")
        self.assertEqual(value["worker_pid"], 222)
        process.wait.assert_not_called()
        process.kill.assert_not_called()

    def test_existing_store_worker_prevents_a_second_purchase(self):
        with patch.object(apps, "_store_lease", side_effect=BlockingIOError(errno.EAGAIN, "busy")), \
             patch.object(apps.subprocess, "Popen") as spawn:
            value = apps._native("store_download", {"app_id": "123", "bundle_id": BUNDLE})
        self.assertEqual(value["reason"], "store_download_pending")
        spawn.assert_not_called()

    def test_failed_store_request_is_not_reported_as_pending(self):
        info = {"status": "verified", "app": {"bundle_id": BUNDLE, "free_offer": True}}
        after = {**state(), "store_request": {"status": "unavailable", "reason": "store_request_failed"}}
        with patch.object(apps, "_get", side_effect=[state(), after]), \
             patch.object(apps, "_native", side_effect=[info, {"status": "partial", "submitted": True}]):
            value = invoke("apps.download", {"source": "app_store", "app_id": "123", "verify_timeout_ms": 0})
        self.assertEqual(value["status"], "unavailable")
        self.assertEqual(value["reason"], "store_request_failed")

    def test_download_bounds_and_checksum(self):
        class Response(io.BytesIO):
            status = 200
            headers = {}
            def geturl(self): return "https://example.com/app.ipa"
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "app.ipa"
            opener = unittest.mock.Mock()
            opener.open.return_value = Response(b"abcde")
            with patch.object(apps.urllib.request, "build_opener", return_value=opener):
                with self.assertRaisesRegex(apps.AppError, "download_size_limit"):
                    apps._download("https://example.com/app.ipa", destination, 4, 2)
        handler = apps.HTTPSRedirects()
        request = apps.urllib.request.Request("https://example.com/app.ipa")
        with self.assertRaises(apps.AppError):
            handler.redirect_request(request, None, 302, "", {}, "http://example.com/app.ipa")

    def test_native_contract_rejects_stale_wrong_target_and_ack_mismatch(self):
        payload = {"schema": apps.SCHEMA, "source": apps.SOURCE, "command": "get", "status": "verified",
                   "bundle_id": BUNDLE, "observed_at_unix": time.time(), "app": state()["app"]}
        for changes, exit_code in [({"bundle_id": "dev.other.app"}, 0), ({"observed_at_unix": 1}, 0),
                                   ({"command": "uninstall"}, 0), ({}, 2)]:
            completed = subprocess.CompletedProcess([], exit_code, json.dumps({**payload, **changes}), "")
            with patch.object(apps.subprocess, "run", return_value=completed):
                result = apps._native("get", {"bundle_id": BUNDLE})
            self.assertEqual(result["status"], "error")

    def test_list_scope_is_incomplete_when_more_results_exist(self):
        with patch.object(apps, "_native", return_value={"status": "verified", "apps": [], "has_more": True}):
            self.assertFalse(invoke("apps.list", {})["complete_for_scope"])


if __name__ == "__main__":
    unittest.main()
