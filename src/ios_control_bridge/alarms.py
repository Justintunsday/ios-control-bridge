"""System Clock alarms through the private MobileTimer framework helper."""
from pathlib import Path
import json
import os
import subprocess
from uuid import UUID

from .device import ios_version
from .result import EXIT_CODES, result

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NATIVE_SCHEMA = "ios-control-bridge.alarms.v1"
NATIVE_SOURCE = "MobileTimer.MTAlarmManager"
VERIFIED_BUILD = ("16.1.1", "20B101")
HELPER_TIMEOUT_SECONDS = 10


def helper_path():
    configured = os.environ.get("ICB_ALARMS_HELPER")
    return Path(configured).expanduser() if configured else PROJECT_ROOT / "build/native/icb-alarms"


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


def _alarm_id(params, request_id):
    value = params.get("alarm_id")
    if not isinstance(value, str):
        return None, result("alarms", "error", reason="invalid_alarm_id", request_id=request_id)
    try:
        return str(UUID(value)).upper(), None
    except (TypeError, ValueError, AttributeError):
        return None, result("alarms", "error", reason="invalid_alarm_id", request_id=request_id)


def _hour_minute(params, required=True):
    hour = params.get("hour")
    minute = params.get("minute")
    if hour is None and minute is None and not required:
        return None, None, None
    if type(hour) is not int or not 0 <= hour <= 23:
        return None, None, "invalid_hour"
    if type(minute) is not int or not 0 <= minute <= 59:
        return None, None, "invalid_minute"
    return hour, minute, None


def list_alarms(params, request_id=None):
    operation = "alarms.list"
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
    alarms = payload.get("alarms")
    if not isinstance(alarms, list):
        return result(operation, "error", reason="native_alarms_invalid", request_id=request_id)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
                  request_id=request_id, complete=True)


def create_alarm(params, request_id=None):
    operation = "alarms.create"
    extra = set(params) - {"hour", "minute", "title"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    hour, minute, invalid = _hour_minute(params)
    if invalid:
        return result(operation, "error", reason=invalid, request_id=request_id)
    title = params.get("title", "Alarm")
    if not isinstance(title, str) or not 1 <= len(title) <= 64:
        return result(operation, "error", reason="invalid_title", request_id=request_id)
    gate = _gate(operation, request_id)
    if gate:
        return gate
    payload, failure = _invoke(["create", str(hour), str(minute), title], operation, request_id)
    if failure:
        return failure
    if payload["status"] != "verified":
        return _failed(operation, payload, request_id)
    alarm = payload.get("alarm")
    if not isinstance(alarm, dict):
        return result(operation, "error", reason="native_alarm_missing", request_id=request_id)
    if alarm.get("hour") != hour or alarm.get("minute") != minute or alarm.get("title") != title:
        return result(operation, "partial", data=payload, reason="readback_mismatch",
                      request_id=request_id, complete=False)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
                  request_id=request_id, complete=True)


def update_alarm(params, request_id=None):
    operation = "alarms.update"
    extra = set(params) - {"alarm_id", "hour", "minute", "title"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    identifier, failure = _alarm_id(params, request_id)
    if failure:
        failure["operation"] = operation
        return failure
    hour = params.get("hour")
    minute = params.get("minute")
    title = params.get("title")
    if hour is None and minute is None and title is None:
        return result(operation, "error", reason="no_changes", request_id=request_id)
    if hour is not None and (type(hour) is not int or not 0 <= hour <= 23):
        return result(operation, "error", reason="invalid_hour", request_id=request_id)
    if minute is not None and (type(minute) is not int or not 0 <= minute <= 59):
        return result(operation, "error", reason="invalid_minute", request_id=request_id)
    if title is not None and (not isinstance(title, str) or not 1 <= len(title) <= 64):
        return result(operation, "error", reason="invalid_title", request_id=request_id)
    gate = _gate(operation, request_id)
    if gate:
        return gate
    listed, failure = _invoke(["list"], operation, request_id)
    if failure:
        return failure
    if listed["status"] != "verified":
        return _failed(operation, listed, request_id)
    current = None
    for row in listed.get("alarms") or []:
        if isinstance(row, dict) and row.get("id") == identifier:
            current = row
            break
    if current is None:
        return result(operation, "error", reason="alarm_not_found", request_id=request_id)
    new_hour = hour if hour is not None else current.get("hour")
    new_minute = minute if minute is not None else current.get("minute")
    new_title = title if title is not None else current.get("title")
    payload, failure = _invoke(["update", identifier, str(new_hour), str(new_minute), str(new_title)],
                               operation, request_id)
    if failure:
        return failure
    if payload["status"] != "verified":
        return _failed(operation, payload, request_id)
    alarm = payload.get("alarm")
    if not isinstance(alarm, dict):
        return result(operation, "error", reason="native_alarm_missing", request_id=request_id)
    if alarm.get("id") != identifier or alarm.get("hour") != new_hour or \
            alarm.get("minute") != new_minute or alarm.get("title") != new_title:
        return result(operation, "partial", data=payload, reason="readback_mismatch",
                      request_id=request_id, complete=False)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
                  request_id=request_id, complete=True)


def set_enabled(params, request_id=None):
    operation = "alarms.set_enabled"
    extra = set(params) - {"alarm_id", "enabled"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    identifier, failure = _alarm_id(params, request_id)
    if failure:
        failure["operation"] = operation
        return failure
    enabled = params.get("enabled")
    if type(enabled) is not bool:
        return result(operation, "error", reason="invalid_enabled", request_id=request_id)
    gate = _gate(operation, request_id)
    if gate:
        return gate
    payload, failure = _invoke(["set_enabled", identifier, "1" if enabled else "0"],
                               operation, request_id)
    if failure:
        return failure
    if payload["status"] != "verified":
        return _failed(operation, payload, request_id)
    alarm = payload.get("alarm")
    if not isinstance(alarm, dict) or alarm.get("id") != identifier:
        return result(operation, "error", reason="native_alarm_missing", request_id=request_id)
    if bool(alarm.get("enabled")) != enabled:
        return result(operation, "partial", data=payload, reason="readback_mismatch",
                      request_id=request_id, complete=False)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
                  request_id=request_id, complete=True)


def delete_alarm(params, request_id=None):
    operation = "alarms.delete"
    extra = set(params) - {"alarm_id"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    identifier, failure = _alarm_id(params, request_id)
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
    if (payload.get("deleted") is not True or payload.get("alarm_id") != identifier
            or payload.get("readback_complete") is not True):
        return result(operation, "error", reason="native_delete_inconsistent", request_id=request_id)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
                  request_id=request_id, complete=True)
