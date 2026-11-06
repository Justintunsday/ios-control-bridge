"""Bounded App Store/IPA installs and exact-ID removal with fresh readback.

LaunchServices may consume an IPA. Only a private disposable copy is passed to it.
An accepted store/install request is never itself proof of an installed app.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import math
import os
import plistlib
import re
import stat
import errno
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from .device import ios_version
from .result import EXIT_CODES, result

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "ios-control-bridge.apps.v1"
SOURCE = "LaunchServices+StoreServices"
VERIFIED_BUILD = ("16.1.1", "20B101")
BUNDLE_ID = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\Z")
DEFAULT_MAX_BYTES = 512 * 1024 * 1024
MAX_BYTES = 2 * 1024 * 1024 * 1024
MAX_MANIFEST = 1024 * 1024


class AppError(ValueError):
    pass


def helper_path():
    return Path(os.environ.get("ICB_APPS_HELPER", str(ROOT / "build/native/icb-apps"))).expanduser()


def readiness():
    version = ios_version()
    if version is None:
        return False, "not_ios"
    if (version.get("ProductVersion"), version.get("ProductBuildVersion")) != VERIFIED_BUILD:
        return False, "unverified_os_build"
    if not helper_path().is_file():
        return False, "native_helper_missing"
    return True, None


def _bundle(value):
    if not isinstance(value, str) or len(value) > 255 or not BUNDLE_ID.fullmatch(value):
        raise AppError("invalid_bundle_id")
    return value


def _integer(params, name, default, low, high):
    value = params.get(name, default)
    if type(value) is not int or not low <= value <= high:
        raise AppError("invalid_" + name)
    return value


def _bool(params, name, default=False):
    value = params.get(name, default)
    if type(value) is not bool:
        raise AppError("invalid_" + name)
    return value


def _installer(params):
    value = params.get("installer", "system")
    if value not in ("system", "trollstore"):
        raise AppError("invalid_installer")
    return value


def _https(url):
    if not isinstance(url, str) or len(url) > 8192 or any(ord(c) < 33 for c in url):
        raise AppError("invalid_url")
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise AppError("invalid_url") from error
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.fragment or port == 0):
        raise AppError("https_url_required")
    return url


class HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 5
    max_repeats = 2

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        _https(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _download(url, destination, limit, timeout):
    _https(url)
    opener = urllib.request.build_opener(HTTPSRedirects())
    deadline = time.monotonic() + timeout
    digest = hashlib.sha256()
    size = 0
    request = urllib.request.Request(url, headers={"User-Agent": "ios-control-bridge/0.13", "Accept": "application/octet-stream"})
    with opener.open(request, timeout=min(timeout, 20)) as response:
        _https(response.geturl())
        if response.status != 200:
            raise AppError("download_http_error")
        length = response.headers.get("Content-Length")
        if length is not None and (not length.isdecimal() or int(length) > limit):
            raise AppError("download_size_limit")
        with destination.open("xb") as stream:
            while True:
                if time.monotonic() >= deadline:
                    raise AppError("download_timeout")
                chunk = response.read(min(65536, limit - size + 1))
                if time.monotonic() >= deadline:
                    raise AppError("download_timeout")
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise AppError("download_size_limit")
                digest.update(chunk)
                stream.write(chunk)
        if length is not None and size != int(length):
            raise AppError("download_incomplete")
    return {"bytes": size, "sha256": digest.hexdigest()}


def inspect_ipa(path, max_bytes=DEFAULT_MAX_BYTES):
    """Inspect the top-level manifest; do not extract untrusted archive members."""
    if not path.is_file() or not 0 < path.stat().st_size <= max_bytes:
        raise AppError("invalid_ipa_size")
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 100000 or sum(e.file_size for e in entries) > min(8 * max_bytes, 8 * MAX_BYTES):
                raise AppError("ipa_expansion_limit")
            manifests = []
            seen = set()
            app_roots = set()
            links = {}
            for entry in entries:
                name = entry.filename
                parts = PurePosixPath(name).parts
                if (not name or name.startswith("/") or "\\" in name or ".." in parts
                        or "\x00" in entry.orig_filename or name in seen or (parts and ":" in parts[0])
                        or any(p in ("", ".") for p in name.rstrip("/").split("/"))):
                    raise AppError("unsafe_ipa_member")
                seen.add(name)
                if stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK):
                    raise AppError("unsupported_ipa_member")
                if len(parts) >= 2 and parts[0] == "Payload" and parts[1].endswith(".app"):
                    app_roots.add(parts[1])
                if stat.S_ISLNK(entry.external_attr >> 16):
                    if entry.file_size > 4096 or entry.is_dir():
                        raise AppError("unsafe_ipa_symlink")
                    target = archive.read(entry).decode("utf-8")
                    if not target or target.startswith("/") or "\\" in target or "\x00" in target:
                        raise AppError("unsafe_ipa_symlink")
                    links[name] = target
                if len(parts) == 3 and parts[0] == "Payload" and parts[1].endswith(".app") and parts[2] == "Info.plist":
                    manifests.append(entry)
            if len(app_roots) != 1 or len(manifests) != 1 or not 0 < manifests[0].file_size <= MAX_MANIFEST:
                raise AppError("invalid_ipa_manifest")
            # Resolve the complete link graph, including symlinked parent paths.
            # A link which looks safe in isolation can otherwise escape via another link.
            for entry in entries:
                pending = list(PurePosixPath(entry.filename).parts)
                # Archives must not also declare children beneath a symlink.
                if any("/".join(pending[:i]) in links for i in range(1, len(pending))):
                    raise AppError("unsafe_ipa_symlink")
                resolved, hops = [], 0
                while pending:
                    part = pending.pop(0)
                    if part in ("", "."):
                        continue
                    if part == "..":
                        if not resolved:
                            raise AppError("unsafe_ipa_symlink")
                        resolved.pop()
                        continue
                    resolved.append(part)
                    target = links.get("/".join(resolved))
                    if target is not None:
                        hops += 1
                        if hops > 40:
                            raise AppError("unsafe_ipa_symlink")
                        resolved.pop()
                        pending = target.split("/") + pending
                original = PurePosixPath(entry.filename).parts
                if len(original) >= 2 and original[0] == "Payload" and tuple(resolved[:2]) != original[:2]:
                    raise AppError("unsafe_ipa_symlink")
            info = plistlib.loads(archive.read(manifests[0]))
            app_root = str(PurePosixPath(manifests[0].filename).parent)
    except (zipfile.BadZipFile, RuntimeError, plistlib.InvalidFileException, EOFError, OSError, ValueError) as error:
        if isinstance(error, AppError):
            raise
        raise AppError("invalid_ipa") from error
    if not isinstance(info, dict):
        raise AppError("invalid_ipa_manifest")
    bundle = _bundle(info.get("CFBundleIdentifier"))
    executable = info.get("CFBundleExecutable")
    version = info.get("CFBundleVersion")
    if (not isinstance(executable, str) or not executable or "/" in executable or "\\" in executable
            or executable in (".", "..") or "\x00" in executable or len(executable) > 255
            or app_root + "/" + executable not in seen or not isinstance(version, str) or not 1 <= len(version) <= 128):
        raise AppError("invalid_ipa_manifest")
    return {"bundle_id": bundle, "version": version,
            "name": str(info.get("CFBundleDisplayName", info.get("CFBundleName", "")))[:256]}


def _store_directory():
    directory = Path(tempfile.gettempdir()) / ("icb-app-store-%d" % os.getuid())
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
        raise OSError("unsafe app store lease directory")
    return directory


def _store_key(bundle):
    return hashlib.sha256(_bundle(bundle).encode("utf-8")).hexdigest()


def _store_lease(bundle):
    """The native worker inherits this lease across exec until its bounded exit."""
    import fcntl  # Device-only; keep the portable catalog importable on Windows.
    descriptor = os.open(str(_store_directory() / (_store_key(bundle) + ".lock")),
                         os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return descriptor
    except OSError:
        os.close(descriptor)
        raise


def _background_store(params, timeout):
    try:
        lease = _store_lease(params["bundle_id"])
    except OSError as error:
        if error.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
            return {"status": "partial", "reason": "store_download_pending", "bundle_id": params["bundle_id"],
                    "next_step": "Complete the existing device confirmation, then call apps.get; do not resubmit."}
        raise
    try:
        output = _store_directory() / (_store_key(params["bundle_id"]) + ".jsonl")
        descriptor = os.open(str(output), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            process = subprocess.Popen([str(helper_path()), "store_download", json.dumps(params, ensure_ascii=True)],
                stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.DEVNULL,
                start_new_session=True, close_fds=True, pass_fds=(lease,))
        deadline = time.monotonic() + timeout
        while True:
            raw = output.read_bytes()
            if len(raw) > 1024 * 1024:
                return {"status": "partial", "reason": "native_output_limit_outcome_unknown", "outcome_unknown": True}
            if b"\n" in raw or process.poll() is not None:
                completed = subprocess.CompletedProcess([], process.poll(), raw.split(b"\n", 1)[0].decode("utf-8"), "")
                completed.worker_pid = process.pid
                return completed
            if time.monotonic() >= deadline:
                return {"status": "partial", "reason": "store_worker_startup_outcome_unknown", "outcome_unknown": True}
            time.sleep(0.05)
    finally:
        os.close(lease)  # The worker retains its inherited reference until it exits.


def _store_state(bundle):
    try:
        if not hasattr(os, "getuid"):
            return None
        path = _store_directory() / (_store_key(bundle) + ".jsonl")
        if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
            return None
        with path.open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536 or not raw.endswith(b"\n"):
            return None
        value = json.loads(raw.splitlines()[-1])
        if (not isinstance(value, dict) or value.get("schema") != SCHEMA or value.get("source") != SOURCE
                or value.get("command") != "store_download" or value.get("bundle_id") != bundle
                or value.get("status") not in ("partial", "unavailable", "error")
                or type(value.get("observed_at_unix")) not in (int, float)
                or not 0 <= time.time() - value["observed_at_unix"] <= 720):
            return None
        return value
    except (OSError, ValueError, TypeError):
        return None


def _native(command, params, timeout=15):
    try:
        if command == "store_download":
            completed = _background_store(params, timeout)
            if isinstance(completed, dict):
                return completed
        else:
            completed = subprocess.run([str(helper_path()), command, json.dumps(params, ensure_ascii=True)],
                                       capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "partial", "reason": "native_timeout_outcome_unknown", "outcome_unknown": True}
    except OSError:
        return {"status": "unavailable", "reason": "native_process_unavailable"}
    except UnicodeError:
        return {"status": "error", "reason": "invalid_native_json"}
    if len(completed.stdout) > 1024 * 1024:
        return {"status": "error", "reason": "native_output_limit"}
    try:
        payload = json.loads(completed.stdout)
    except (ValueError, TypeError):
        return {"status": "error", "reason": "invalid_native_json"}
    if (not isinstance(payload, dict) or payload.get("schema") != SCHEMA or payload.get("source") != SOURCE
            or payload.get("command") != command or not isinstance(payload.get("status"), str)
            or payload["status"] not in EXIT_CODES
            or type(payload.get("observed_at_unix")) not in (int, float)
            or not math.isfinite(payload["observed_at_unix"])
            or abs(time.time() - payload["observed_at_unix"]) > timeout + 10):
        return {"status": "error", "reason": "invalid_native_contract"}
    if completed.returncode is None:
        if (command != "store_download" or payload["status"] != "partial" or payload.get("submitted") is not True
                or type(payload.get("worker_pid")) is not int or payload["worker_pid"] <= 0
                or payload["worker_pid"] != getattr(completed, "worker_pid", None)
                or type(payload.get("worker_expires_at_unix")) not in (int, float)
                or not 0 < payload["worker_expires_at_unix"] - time.time() <= 610):
            return {"status": "error", "reason": "invalid_native_worker_contract"}
    elif completed.returncode != EXIT_CODES[payload["status"]]:
        return {"status": "error", "reason": "native_exit_status_mismatch"}
    if "bundle_id" in params and payload.get("bundle_id") != params["bundle_id"]:
        return {"status": "error", "reason": "native_target_mismatch"}
    if "app_id" in params and payload.get("app_id") != params["app_id"]:
        return {"status": "error", "reason": "native_target_mismatch"}
    return payload


def _get(bundle):
    payload = _native("get", {"bundle_id": bundle})
    app = payload.get("app")
    if payload["status"] == "verified" and (not isinstance(app, dict) or app.get("bundle_id") != bundle
            or type(app.get("installed")) is not bool or type(app.get("placeholder")) is not bool
            or type(app.get("protected")) is not bool):
        return {"status": "error", "reason": "invalid_app_readback"}
    state = _store_state(bundle)
    if state:
        payload["store_request"] = state
    return payload


def _finish(operation, payload, request_id, **extra):
    data = dict(payload, **extra)
    return result(operation, payload["status"], data=data, reason=payload.get("reason"), source=SOURCE,
                  request_id=request_id, complete=payload["status"] == "verified")


def _observe(bundle, timeout, desired, version=None, *, store=False):
    deadline = time.monotonic() + timeout
    while True:
        payload = _get(bundle)  # New native process; LaunchServices proxy caches cannot prove a write.
        app = payload.get("app", {})
        if payload["status"] == "verified" and app.get("installed") is desired:
            if not app.get("placeholder") and (not desired or version is None or app.get("version") == version):
                return True, payload
        if store and payload.get("store_request", {}).get("status") in ("error", "unavailable"):
            return False, payload
        if time.monotonic() >= deadline or payload["status"] in ("error", "unavailable"):
            return False, payload
        time.sleep(min(0.5, max(0, deadline - time.monotonic())))


def _mutation(operation, command, params, bundle, verify_ms, request_id, version=None, metadata=None):
    native_timeout = 30
    if command == "install" or params.get("installer") == "trollstore":
        native_timeout = 90  # Covers the helper's own 60-second child-process deadline.
    elif command == "store_download":
        native_timeout = 65
    ack = _native(command, params, timeout=native_timeout)
    if ack["status"] in ("error", "unavailable") or (not ack.get("accepted") and not ack.get("submitted") and not ack.get("outcome_unknown")):
        return _finish(operation, ack, request_id, **(metadata or {}))
    verified, after = _observe(bundle, verify_ms / 1000, command != "uninstall", version, store=command == "store_download")
    data = {"bundle_id": bundle, "request": ack, "readback": after,
            "changed": True if verified else None, **(metadata or {})}
    failed_store = not verified and command == "store_download" and after.get("store_request", {}).get("status") in ("error", "unavailable")
    if not verified and command == "store_download" and not failed_store:
        data["next_step"] = "Complete any App Store confirmation on the device, then call apps.get for this bundle_id; do not resubmit this download."
    return result(operation, "verified" if verified else "unavailable" if failed_store else "partial", request_id=request_id,
                  source=SOURCE, complete=verified,
                  reason=None if verified else "store_request_failed" if failed_store else "store_download_pending" if command == "store_download" else "readback_not_confirmed",
                  data=data)


def _install(operation, path, params, request_id, download=None):
    limit = _integer(params, "max_bytes", DEFAULT_MAX_BYTES, 1, MAX_BYTES)
    replace = _bool(params, "replace")
    installer = _installer(params)
    verify_ms = _integer(params, "verify_timeout_ms", 15000, 0, 120000)
    manifest = inspect_ipa(path, limit)
    if params.get("bundle_id") is not None and _bundle(params["bundle_id"]) != manifest["bundle_id"]:
        raise AppError("ipa_bundle_id_mismatch")
    bundle = manifest["bundle_id"]
    before = _get(bundle)
    if before["status"] != "verified":
        return _finish(operation, before, request_id)
    if before["app"]["protected"]:
        raise AppError("protected_app")
    if before["app"]["installed"] and not replace:
        raise AppError("app_already_installed")
    with tempfile.TemporaryDirectory(prefix="icb-install-") as temporary:
        disposable = Path(temporary) / "payload.ipa"
        copied = 0
        with path.open("rb") as original, disposable.open("xb") as copy:
            for chunk in iter(lambda: original.read(65536), b""):
                copied += len(chunk)
                if copied > limit:
                    raise AppError("invalid_ipa_size")
                copy.write(chunk)
        # Inspect the copy actually passed to installd, not a possibly changing source.
        if inspect_ipa(disposable, limit) != manifest:
            raise AppError("ipa_changed_before_install")
        digest = hashlib.sha256()
        with disposable.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        expected = params.get("sha256")
        if expected is not None and (not isinstance(expected, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected)
                                     or expected.lower() != digest.hexdigest()):
            raise AppError("ipa_sha256_mismatch")
        return _mutation(operation, "install", {"path": str(disposable), "bundle_id": bundle, "replace": replace, "installer": installer},
                         bundle, verify_ms, request_id, manifest["version"],
                         {"ipa": manifest, "sha256": digest.hexdigest(), "download": download})


def _store_id(params):
    app_id = params.get("app_id")
    url = params.get("url")
    if app_id is not None and url is not None:
        raise AppError("choose_app_id_or_url")
    if url is not None:
        parsed = urllib.parse.urlsplit(_https(url))
        match = re.search(r"/id([1-9][0-9]{0,18})(?:/|$)", parsed.path)
        if parsed.hostname != "apps.apple.com" or parsed.port not in (None, 443) or not match:
            raise AppError("invalid_app_store_url")
        app_id = match.group(1)
    if type(app_id) is int:
        app_id = str(app_id)
    if not isinstance(app_id, str) or not re.fullmatch(r"[1-9][0-9]{0,18}", app_id):
        raise AppError("invalid_app_id")
    return app_id


def call(operation, params, request_id=None):
    command = operation.split(".", 1)[1]
    allowed = {
        "list": {"query", "include_system", "limit", "offset"}, "get": {"bundle_id"},
        "install": {"path", "bundle_id", "replace", "sha256", "max_bytes", "verify_timeout_ms", "installer"},
        "uninstall": {"bundle_id", "verify_timeout_ms", "installer"}, "store_info": {"app_id", "url"},
        "download": {"source", "url", "app_id", "bundle_id", "replace", "sha256", "max_bytes",
                     "download_timeout_ms", "verify_timeout_ms", "installer"},
    }
    try:
        if command not in allowed or set(params) - allowed[command]:
            raise AppError("unknown_parameters")
        # Validate caller input even when no device is connected.
        if command in ("get", "uninstall"):
            bundle = _bundle(params.get("bundle_id"))
        if command == "list":
            query = params.get("query", "")
            if not isinstance(query, str) or len(query) > 128:
                raise AppError("invalid_query")
            native_params = {"query": query, "include_system": _bool(params, "include_system"),
                             "limit": _integer(params, "limit", 50, 1, 500),
                             "offset": _integer(params, "offset", 0, 0, 100000)}
        if command in ("install", "uninstall", "download"):
            verify_ms = _integer(params, "verify_timeout_ms", 15000, 0, 120000)
            _installer(params)
        if command in ("install", "download"):
            _bool(params, "replace")
            _integer(params, "max_bytes", DEFAULT_MAX_BYTES, 1, MAX_BYTES)
            if "sha256" in params and (not isinstance(params["sha256"], str) or not re.fullmatch(r"[a-fA-F0-9]{64}", params["sha256"])):
                raise AppError("invalid_sha256")
        if command == "install":
            value = params.get("path")
            if not isinstance(value, str) or not Path(value).is_absolute():
                raise AppError("absolute_ipa_path_required")
            path = Path(value)
        if command == "store_info" or (command == "download" and params.get("source") == "app_store"):
            app_id = _store_id(params)
            if set(params) - {"source", "app_id", "url", "bundle_id", "verify_timeout_ms"}:
                raise AppError("unsupported_app_store_parameters")
        if command == "download":
            source = params.get("source")
            if source not in ("ipa", "app_store"):
                raise AppError("invalid_source")
            if source == "ipa":
                if "app_id" in params:
                    raise AppError("unsupported_ipa_parameters")
                url = _https(params.get("url"))
                limit = _integer(params, "max_bytes", DEFAULT_MAX_BYTES, 1, MAX_BYTES)
                timeout = _integer(params, "download_timeout_ms", 120000, 1000, 600000) / 1000
        ready, reason = readiness()
        if not ready:
            return result(operation, "unavailable", reason=reason, request_id=request_id)
        if command == "get":
            return _finish(operation, _get(bundle), request_id)
        if command == "list":
            payload = _native("list", native_params)
            if payload["status"] == "verified" and (not isinstance(payload.get("apps"), list)
                    or len(payload["apps"]) > native_params["limit"] or type(payload.get("has_more")) is not bool):
                raise AppError("invalid_native_app_list")
            value = _finish(operation, payload, request_id)
            value["complete_for_scope"] = payload["status"] == "verified" and payload.get("has_more") is False
            return value
        if command == "install":
            return _install(operation, path, params, request_id)
        if command == "uninstall":
            before = _get(bundle)
            if before["status"] != "verified":
                return _finish(operation, before, request_id)
            if before["app"]["protected"]:
                raise AppError("protected_app")
            if not before["app"]["installed"] and not before["app"]["placeholder"]:
                return _finish(operation, before, request_id, changed=False)
            return _mutation(operation, "uninstall", {"bundle_id": bundle, "installer": _installer(params)}, bundle, verify_ms, request_id)
        if command == "store_info" or source == "app_store":
            info = _native("store_info", {"app_id": app_id}, timeout=30)
            if info["status"] != "verified":
                return _finish(operation, info, request_id)
            app = info.get("app", {})
            bundle = _bundle(app.get("bundle_id"))
            if command == "store_info":
                return _finish(operation, info, request_id)
            if params.get("bundle_id") is not None and _bundle(params["bundle_id"]) != bundle:
                raise AppError("app_store_bundle_id_mismatch")
            if app.get("free_offer") is not True:
                return result(operation, "unavailable", reason="free_offer_required", data=info, request_id=request_id)
            before = _get(bundle)
            if before["status"] != "verified":
                return _finish(operation, before, request_id)
            if before["app"]["installed"] and not before["app"]["placeholder"]:
                return _finish(operation, before, request_id, changed=False, store=app)
            if before["app"]["placeholder"]:
                return result(operation, "partial", reason="store_download_pending", request_id=request_id,
                              source=SOURCE, data={"bundle_id": bundle, "readback": before, "store": app,
                                  "next_step": "Inspect the existing App Store download on the device, then call apps.get; do not resubmit this download."})
            # Helper obtains a fresh Apple offer and checks its price again before the request.
            return _mutation(operation, "store_download", {"app_id": app_id, "bundle_id": bundle},
                             bundle, verify_ms, request_id, metadata={"store": app})
        with tempfile.TemporaryDirectory(prefix="icb-download-") as temporary:
            path = Path(temporary) / "download.ipa"
            download = _download(url, path, limit, timeout)
            return _install(operation, path, params, request_id, download)
    except AppError as error:
        return result(operation, "error", reason=str(error), request_id=request_id)
    except (urllib.error.URLError, TimeoutError, OSError):
        return result(operation, "unavailable", reason="download_or_file_unavailable", request_id=request_id)
