"""ReminderKit adapter for system Reminders.

EventKit on this device exposed zero reminder lists while ReminderKit's private
REMStore correctly returned the account and the user's Reminders list, so this
adapter uses the private framework through a signed helper.
"""
from pathlib import Path
import json
import os
import subprocess
from uuid import UUID

from .device import ios_version
from .result import EXIT_CODES, result

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NATIVE_SCHEMA = "ios-control-bridge.reminders.v1"
NATIVE_SOURCE = "ReminderKit.REMStore"
VERIFIED_BUILD = ("16.1.1", "20B101")
HELPER_TIMEOUT_SECONDS = 12


def helper_path():
    configured = os.environ.get("ICB_REMINDERS_HELPER")
    if configured:
        return Path(configured).expanduser()
    installed = Path("/var/jb/usr/local/bin/icb-reminders")
    if installed.is_file():
        return installed
    return PROJECT_ROOT / "build/native/icb-reminders"


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


def _uuid(params, key, request_id):
    value = params.get(key)
    if not isinstance(value, str):
        return None, result("reminders", "error", reason="invalid_" + key, request_id=request_id)
    try:
        return str(UUID(value)).upper(), None
    except (TypeError, ValueError, AttributeError):
        return None, result("reminders", "error", reason="invalid_" + key, request_id=request_id)


def _title(params, request_id):
    value = params.get("title")
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        return None, result("reminders", "error", reason="invalid_title", request_id=request_id)
    return value, None


def list_lists(params, request_id=None):
    operation = "reminders.lists"
    if params:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    gate = _gate(operation, request_id)
    if gate:
        return gate
    payload, failure = _invoke(["lists"], operation, request_id)
    if failure:
        return failure
    if payload["status"] != "verified":
        return _failed(operation, payload, request_id)
    if not isinstance(payload.get("lists"), list):
        return result(operation, "error", reason="native_lists_invalid", request_id=request_id)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
                  request_id=request_id, complete=True)


def list_reminders(params, request_id=None):
    operation = "reminders.list"
    extra = set(params) - {"list_id"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    identifier, failure = _uuid(params, "list_id", request_id)
    if failure:
        failure["operation"] = operation
        return failure
    gate = _gate(operation, request_id)
    if gate:
        return gate
    payload, failure = _invoke(["list", identifier], operation, request_id)
    if failure:
        return failure
    if payload["status"] != "verified":
        return _failed(operation, payload, request_id)
    if not isinstance(payload.get("reminders"), list):
        return result(operation, "error", reason="native_reminders_invalid", request_id=request_id)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
                  request_id=request_id, complete=True)


def create_reminder(params, request_id=None):
    operation = "reminders.create"
    extra = set(params) - {"list_id", "title"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    identifier, failure = _uuid(params, "list_id", request_id)
    if failure:
        failure["operation"] = operation
        return failure
    title, failure = _title(params, request_id)
    if failure:
        failure["operation"] = operation
        return failure
    gate = _gate(operation, request_id)
    if gate:
        return gate
    payload, failure = _invoke(["create", identifier, title], operation, request_id)
    if failure:
        return failure
    if payload["status"] != "verified":
        return _failed(operation, payload, request_id)
    reminder = payload.get("reminder")
    if not isinstance(reminder, dict) or reminder.get("title") != title:
        return result(operation, "partial", data=payload, reason="readback_mismatch",
                      request_id=request_id, complete=False)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
                  request_id=request_id, complete=True)


def update_reminder(params, request_id=None):
    operation = "reminders.update"
    extra = set(params) - {"reminder_id", "title"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    identifier, failure = _uuid(params, "reminder_id", request_id)
    if failure:
        failure["operation"] = operation
        return failure
    title, failure = _title(params, request_id)
    if failure:
        failure["operation"] = operation
        return failure
    gate = _gate(operation, request_id)
    if gate:
        return gate
    payload, failure = _invoke(["update", identifier, title], operation, request_id)
    if failure:
        return failure
    if payload["status"] != "verified":
        return _failed(operation, payload, request_id)
    reminder = payload.get("reminder")
    if not isinstance(reminder, dict) or reminder.get("id") != identifier or reminder.get("title") != title:
        return result(operation, "partial", data=payload, reason="readback_mismatch",
                      request_id=request_id, complete=False)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
                  request_id=request_id, complete=True)


def complete_reminder(params, request_id=None):
    operation = "reminders.complete"
    extra = set(params) - {"reminder_id"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    identifier, failure = _uuid(params, "reminder_id", request_id)
    if failure:
        failure["operation"] = operation
        return failure
    gate = _gate(operation, request_id)
    if gate:
        return gate
    payload, failure = _invoke(["complete", identifier], operation, request_id)
    if failure:
        return failure
    if payload["status"] != "verified":
        return _failed(operation, payload, request_id)
    reminder = payload.get("reminder")
    if not isinstance(reminder, dict) or reminder.get("id") != identifier or reminder.get("completed") is not True:
        return result(operation, "partial", data=payload, reason="readback_mismatch",
                      request_id=request_id, complete=False)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
                  request_id=request_id, complete=True)


def delete_reminder(params, request_id=None):
    operation = "reminders.delete"
    extra = set(params) - {"reminder_id"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    identifier, failure = _uuid(params, "reminder_id", request_id)
    if failure:
        failure["operation"] = operation
        return failure
    gate = _gate(operation, request_id)
    if gate:
        return gate
    payload, failure = _invoke(["delete", identifier], operation, request_id)
    if failure:
        return failure
    if payload["status"] != "verified":
        return _failed(operation, payload, request_id)
    if payload.get("deleted") is not True or payload.get("reminder_id") != identifier:
        return result(operation, "error", reason="native_delete_inconsistent", request_id=request_id)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
                  request_id=request_id, complete=True)
