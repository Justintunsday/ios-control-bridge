"""Read and write supported settings, with a device readback boundary."""
from pathlib import Path
import json
import math
import os
import subprocess

from . import ellekit_bridge
from .device import ios_version
from .result import EXIT_CODES, result

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NATIVE_SCHEMA = "ios-control-bridge.settings.v1"
NATIVE_SETTINGS = ("volume", "brightness")
BOOLEAN_SETTINGS = ("low_power", "orientation_lock")
SUPPORTED_SETTINGS = NATIVE_SETTINGS + BOOLEAN_SETTINGS
SETTING_SOURCES = {
    "volume": "AVSystemController",
    "brightness": "BrightnessSystemClient",
    "low_power": "ellekit.springboard",
    "orientation_lock": "ellekit.springboard",
}
SETTING_TOLERANCES = {
    "volume": 0.001,
    "brightness": 0.005,
}
VERIFIED_BUILD = ("16.1.1", "20B101")
HELPER_TIMEOUT_SECONDS = 10


def helper_path():
    configured = os.environ.get("ICB_SETTINGS_HELPER")
    return Path(configured).expanduser() if configured else PROJECT_ROOT / "build/native/icb-settings"


def available_settings():
    settings = []
    if helper_path().is_file():
        settings.extend(NATIVE_SETTINGS)
    if ellekit_bridge.available():
        settings.extend(BOOLEAN_SETTINGS)
    return settings


def _unsupported_setting(operation, setting, request_id):
    return result(operation, "unavailable", reason="unsupported_setting",
                  data={"setting": setting, "supported_settings": list(SUPPORTED_SETTINGS),
                        "available_settings": available_settings()},
                  request_id=request_id)


def _runtime_gate(operation, setting, request_id):
    version = ios_version()
    if version is None:
        return result(operation, "unavailable", reason="not_ios", request_id=request_id)
    if (version.get("ProductVersion"), version.get("ProductBuildVersion")) != VERIFIED_BUILD:
        return result(operation, "unavailable", reason="unverified_os_build", request_id=request_id)
    if setting in NATIVE_SETTINGS and not helper_path().is_file():
        return result(operation, "unavailable", reason="native_helper_missing", request_id=request_id)
    if setting in BOOLEAN_SETTINGS and not ellekit_bridge.available():
        return result(operation, "unavailable", reason="ellekit_bridge_unavailable", request_id=request_id)
    return None


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _invoke(arguments, operation, request_id, expected_source):
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
    if payload.get("source") != expected_source:
        return None, result(operation, "error", reason="native_source_mismatch", request_id=request_id)
    if payload.get("setting") != arguments[1]:
        return None, result(operation, "error", reason="native_setting_mismatch", request_id=request_id)
    if payload.get("status") not in EXIT_CODES:
        return None, result(operation, "error", reason="native_status_invalid", request_id=request_id)
    if completed.returncode != EXIT_CODES[payload["status"]]:
        return None, result(operation, "error", reason="native_exit_status_mismatch", request_id=request_id)
    return payload, None


def _bridge_failure(operation, bridge_result, request_id):
    status = bridge_result.get("status")
    mapped = {"ok": "verified", "unavailable": "unavailable", "error": "error"}.get(status)
    if mapped is None:
        return result(operation, "error", reason="native_status_invalid", request_id=request_id)
    return result(operation, mapped, reason=bridge_result.get("detail") or "bridge_failure",
                  data={"bridge": bridge_result}, request_id=request_id)


def _bridge_get(operation, setting, request_id):
    bridge_result = ellekit_bridge.request("get_" + setting)
    if bridge_result.get("status") != "ok":
        return _bridge_failure(operation, bridge_result, request_id)
    value = bridge_result.get("value")
    if value not in (0, 1):
        return result(operation, "error", reason="native_value_invalid", request_id=request_id)
    return result(operation, "verified", request_id=request_id, complete=True,
                  data={"setting": setting, "value": bool(value),
                        "detail": bridge_result.get("detail", ""),
                        "source": SETTING_SOURCES[setting]},
                  source=SETTING_SOURCES[setting])


def _native_get(operation, setting, request_id):
    payload, failure = _invoke(["get", setting], operation, request_id, SETTING_SOURCES[setting])
    if failure:
        return failure
    if payload.get("status") != "verified":
        return result(operation, payload["status"], data=payload, reason=payload.get("reason"),
                      request_id=request_id, complete=False)
    value = payload.get("value")
    if not _number(value) or not 0.0 <= value <= 1.0:
        return result(operation, "error", reason="native_value_invalid", request_id=request_id)
    return result(operation, "verified", data=payload, source=SETTING_SOURCES[setting],
                  request_id=request_id, complete=True)


def _get(params, request_id):
    operation = "settings.get"
    extra = set(params) - {"setting"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    setting = params.get("setting")
    if not isinstance(setting, str):
        return result(operation, "error", reason="invalid_setting", request_id=request_id)
    if setting not in SUPPORTED_SETTINGS:
        return _unsupported_setting(operation, setting, request_id)
    gate = _runtime_gate(operation, setting, request_id)
    if gate:
        return gate
    if setting in BOOLEAN_SETTINGS:
        return _bridge_get(operation, setting, request_id)
    return _native_get(operation, setting, request_id)


def _native_set(operation, setting, value, request_id):
    payload, failure = _invoke(["set", setting, format(float(value), ".9f")], operation,
                               request_id, SETTING_SOURCES[setting])
    if failure:
        return failure
    if payload.get("status") != "verified":
        return result(operation, payload["status"], data=payload, reason=payload.get("reason"),
                      request_id=request_id, complete=False)
    before = payload.get("before")
    requested = payload.get("requested")
    readback = payload.get("readback")
    if not (_number(before) and _number(requested) and _number(readback)):
        return result(operation, "error", reason="native_readback_invalid", request_id=request_id)
    if abs(requested - value) > 1e-6:
        return result(operation, "error", reason="native_requested_mismatch", request_id=request_id)
    if abs(readback - requested) > SETTING_TOLERANCES[setting] + 1e-9:
        return result(operation, "partial", data=payload, reason="readback_mismatch",
                      request_id=request_id, complete=False)
    return result(operation, "verified", data=payload, source=SETTING_SOURCES[setting],
                  request_id=request_id, complete=True)


def _bridge_set(operation, setting, value, request_id):
    before = ellekit_bridge.request("get_" + setting)
    if before.get("status") != "ok" or before.get("value") not in (0, 1):
        return _bridge_failure(operation, before, request_id)
    command = ellekit_bridge.request("set_" + setting, 1 if value else 0)
    if command.get("status") != "ok":
        return _bridge_failure(operation, command, request_id)
    readback = ellekit_bridge.request("get_" + setting)
    if readback.get("status") != "ok" or readback.get("value") not in (0, 1):
        return _bridge_failure(operation, readback, request_id)
    requested = bool(value)
    actual = bool(readback["value"])
    data = {"setting": setting, "before": bool(before["value"]), "requested": requested,
            "readback": actual, "detail": readback.get("detail", ""),
            "source": SETTING_SOURCES[setting]}
    if actual != requested:
        return result(operation, "partial", data=data, reason="readback_mismatch",
                      request_id=request_id, complete=False)
    return result(operation, "verified", data=data, source=SETTING_SOURCES[setting],
                  request_id=request_id, complete=True)


def _set(params, request_id):
    operation = "settings.set"
    extra = set(params) - {"setting", "value"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    setting = params.get("setting")
    if not isinstance(setting, str):
        return result(operation, "error", reason="invalid_setting", request_id=request_id)
    if setting not in SUPPORTED_SETTINGS:
        return _unsupported_setting(operation, setting, request_id)
    if "value" not in params:
        return result(operation, "error", reason="missing_value", request_id=request_id)
    value = params["value"]
    if setting in BOOLEAN_SETTINGS:
        if type(value) is not bool:
            return result(operation, "error", reason="invalid_value", request_id=request_id)
    elif not _number(value) or not 0.0 <= value <= 1.0:
        return result(operation, "error", reason="invalid_value", request_id=request_id)
    gate = _runtime_gate(operation, setting, request_id)
    if gate:
        return gate
    if setting in BOOLEAN_SETTINGS:
        return _bridge_set(operation, setting, value, request_id)
    return _native_set(operation, setting, value, request_id)


def get_setting(params, request_id=None):
    return _get(params, request_id)


def set_setting(params, request_id=None):
    return _set(params, request_id)
