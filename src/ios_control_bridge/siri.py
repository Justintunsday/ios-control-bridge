"""Siri language settings through a measured, mobile-user native helper."""
import json
import os
from pathlib import Path
import subprocess
import time

from .device import ios_version
from .result import EXIT_CODES, result

SCHEMA = "ios-control-bridge.siri-language.v1"
SOURCE = "AssistantServices.AFPreferences"
LANGUAGES = ("zh-CN", "en-US")


def helper_path():
    configured = os.environ.get("ICB_SIRI_LANGUAGE_HELPER")
    return Path(configured).expanduser() if configured else Path("/var/jb/usr/local/bin/icb-siri-language")


def readiness():
    version = ios_version()
    if version is None:
        return False, "not_ios"
    if (version.get("ProductVersion"), version.get("ProductBuildVersion")) != ("16.1.1", "20B101"):
        return False, "unverified_os_build"
    if not helper_path().is_file():
        return False, "native_helper_missing"
    return True, None


def _invoke(arguments):
    command = [str(helper_path()), *arguments]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        command = ["/var/jb/usr/bin/sudo", "-H", "-u", "mobile", *command]
    try:
        response = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
    except subprocess.TimeoutExpired:
        return None, "native_process_timeout"
    except OSError:
        return None, "native_process_unavailable"
    if len(response.stdout.encode("utf8")) > 16384:
        return None, "native_output_limit"
    try:
        value = json.loads(response.stdout)
    except (ValueError, TypeError):
        return None, "invalid_native_json"
    if (not isinstance(value, dict) or value.get("schema") != SCHEMA or value.get("source") != SOURCE
            or value.get("status") not in EXIT_CODES or response.returncode != EXIT_CODES[value["status"]]):
        return None, "native_response_mismatch"
    return value, None


def language(params, request_id=None, *, write=False):
    operation = "siri.language.set" if write else "siri.language.get"
    if set(params) - ({"language_code"} if write else set()):
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    requested = params.get("language_code")
    if write and (not isinstance(requested, str) or requested not in LANGUAGES):
        return result(operation, "error", reason="unsupported_language", request_id=request_id)
    ready, reason = readiness()
    if not ready:
        return result(operation, "unavailable", reason=reason, request_id=request_id)
    value, failure = _invoke(["set-language", requested] if write else ["get"])
    if failure:
        return result(operation, "unavailable", reason=failure, request_id=request_id)
    delayed = write and value["status"] == "partial" and value.get("reason") == "readback_mismatch"
    if value["status"] != "verified" and not delayed:
        return result(operation, value["status"], data=value, reason=value.get("reason"), request_id=request_id)
    if not isinstance(value.get("language_code"), str) or not value["language_code"]:
        return result(operation, "error", reason="invalid_language_readback", request_id=request_id)
    if write:
        if (value.get("requested") != requested or not isinstance(value.get("before"), str)
                or (not delayed and (value.get("readback") != requested or value["language_code"] != requested))):
            return result(operation, "partial", data=value, reason="readback_mismatch", request_id=request_id)
        matched = False
        for attempt in range(3 if delayed else 1):
            observed, failure = _invoke(["get"])
            if not failure and observed.get("status") == "verified" and observed.get("language_code") == requested:
                matched = True
                break
            if failure:
                break
            if delayed and attempt < 2:
                time.sleep(.1)
        if not matched:
            return result(operation, "partial", data=value, reason="independent_readback_failed", request_id=request_id)
        if delayed:
            value.update(native_cached_readback=value.get("readback"), readback=requested,
                         language_code=requested, status="verified")
            value.pop("reason", None)
        value["independent_readback"] = observed["language_code"]
    return result(operation, "verified", data=value, source=SOURCE, request_id=request_id, complete=True)
