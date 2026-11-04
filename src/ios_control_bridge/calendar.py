"""EventKit calendar adapter with explicit source selection and readback."""
from pathlib import Path
import json
import os
import subprocess
from uuid import UUID

from .device import ios_version
from .result import EXIT_CODES, result

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NATIVE_SCHEMA = "ios-control-bridge.calendar.v1"
NATIVE_SOURCE = "EventKit.EKEventStore"
VERIFIED_BUILD = ("16.1.1", "20B101")
HELPER_TIMEOUT_SECONDS = 12


def helper_path():
    configured = os.environ.get("ICB_CALENDAR_HELPER")
    if configured:
        return Path(configured).expanduser()
    installed = Path("/var/jb/usr/local/bin/icb-calendar")
    if installed.is_file():
        return installed
    return PROJECT_ROOT / "build/native/icb-calendar"


def _gate(operation, request_id):
    version = ios_version()
    if version is None:
        return result(operation, "unavailable", reason="not_ios", request_id=request_id)
    if (version.get("ProductVersion"), version.get("ProductBuildVersion")) != VERIFIED_BUILD:
        return result(operation, "unavailable", reason="unverified_os_build", request_id=request_id)
    if not helper_path().is_file():
        return result(operation, "unavailable", reason="native_helper_missing", request_id=request_id)
    return None


def _invoke(arguments, operation, request_id):
    try:
        completed = subprocess.run([str(helper_path())] + arguments, capture_output=True,
                                   text=True, timeout=HELPER_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        return None, result(operation, "unavailable", reason="native_process_timeout", request_id=request_id)
    except OSError:
        return None, result(operation, "unavailable", reason="native_process_unavailable", request_id=request_id)
    if len(completed.stdout.encode("utf8")) > 524288:
        return None, result(operation, "partial", reason="native_output_limit", request_id=request_id)
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, ValueError):
        return None, result(operation, "error", reason="invalid_native_json", request_id=request_id)
    if not isinstance(payload, dict) or payload.get("schema") != NATIVE_SCHEMA:
        return None, result(operation, "error", reason="native_schema_mismatch", request_id=request_id)
    if payload.get("source") != NATIVE_SOURCE:
        return None, result(operation, "error", reason="native_source_mismatch", request_id=request_id)
    if payload.get("status") not in EXIT_CODES:
        return None, result(operation, "error", reason="native_status_invalid", request_id=request_id)
    if completed.returncode != EXIT_CODES[payload["status"]]:
        return None, result(operation, "error", reason="native_exit_status_mismatch", request_id=request_id)
    return payload, None


def _failed(operation, payload, request_id):
    return result(operation, payload["status"], data=payload, reason=payload.get("reason"),
                  request_id=request_id, complete=False)


def list_calendars(params, request_id=None):
    operation = "calendar.list"
    if params:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    gate = _gate(operation, request_id)
    if gate:
        return gate
    payload, failure = _invoke(["list"], operation, request_id)
    if failure:
        return failure
    if payload["status"] != "verified":
        return _failed(operation, payload, request_id)
    if not isinstance(payload.get("calendars"), list):
        return result(operation, "error", reason="native_calendars_invalid", request_id=request_id)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
                  request_id=request_id, complete=True)


def create_calendar(params, request_id=None):
    operation = "calendar.create"
    extra = set(params) - {"title", "source_id"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    title = params.get("title")
    if not isinstance(title, str) or not 1 <= len(title) <= 64:
        return result(operation, "error", reason="invalid_title", request_id=request_id)
    source_id = params.get("source_id")
    if source_id is not None and (not isinstance(source_id, str) or not source_id):
        return result(operation, "error", reason="invalid_source_id", request_id=request_id)
    gate = _gate(operation, request_id)
    if gate:
        return gate
    arguments = ["create", title] + ([source_id] if source_id else [])
    payload, failure = _invoke(arguments, operation, request_id)
    if failure:
        return failure
    if payload["status"] != "verified":
        return _failed(operation, payload, request_id)
    calendar = payload.get("calendar")
    if not isinstance(calendar, dict) or calendar.get("title") != title:
        return result(operation, "partial", data=payload, reason="readback_mismatch",
                      request_id=request_id, complete=False)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
                  request_id=request_id, complete=True)


def delete_calendar(params, request_id=None):
    operation = "calendar.delete"
    extra = set(params) - {"calendar_id"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    value = params.get("calendar_id")
    if not isinstance(value, str):
        return result(operation, "error", reason="invalid_calendar_id", request_id=request_id)
    try:
        identifier = str(UUID(value)).upper()
    except (TypeError, ValueError, AttributeError):
        return result(operation, "error", reason="invalid_calendar_id", request_id=request_id)
    gate = _gate(operation, request_id)
    if gate:
        return gate
    payload, failure = _invoke(["delete", identifier], operation, request_id)
    if failure:
        return failure
    if payload["status"] != "verified":
        return _failed(operation, payload, request_id)
    if payload.get("deleted") is not True or payload.get("calendar_id") != identifier:
        return result(operation, "error", reason="native_delete_inconsistent", request_id=request_id)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
                  request_id=request_id, complete=True)
