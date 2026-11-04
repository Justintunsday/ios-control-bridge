"""Read and write a supported system setting, with a device readback boundary."""
from pathlib import Path
import json
import math
import os
import subprocess

from .device import ios_version
from .result import EXIT_CODES, result

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NATIVE_SCHEMA = "ios-control-bridge.settings.v1"
NATIVE_SOURCE = "AVSystemController"
VERIFIED_BUILD = ("16.1.1", "20B101")
SUPPORTED_SETTINGS = ("volume",)
VOLUME_TOLERANCE = 0.001
HELPER_TIMEOUT_SECONDS = 10


def helper_path():
    configured = os.environ.get("ICB_SETTINGS_HELPER")
    return Path(configured).expanduser() if configured else PROJECT_ROOT / "build/native/icb-settings"


def _unsupported_setting(operation, setting, request_id):
    return result(operation, "unavailable", reason="unsupported_setting",
                  data={"setting": setting, "supported_settings": list(SUPPORTED_SETTINGS)},
                  request_id=request_id)


def _runtime_gate(operation, request_id):
    version = ios_version()
    if version is None:
        return result(operation, "unavailable", reason="not_ios", request_id=request_id)
    if (version.get("ProductVersion"), version.get("ProductBuildVersion")) != VERIFIED_BUILD:
        return result(operation, "unavailable", reason="unverified_os_build", request_id=request_id)
    if not helper_path().is_file():
        return result(operation, "unavailable", reason="native_helper_missing", request_id=request_id)
    return None


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


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
    if payload.get("setting") != arguments[1]:
        return None, result(operation, "error", reason="native_setting_mismatch", request_id=request_id)
    if payload.get("status") not in EXIT_CODES:
        return None, result(operation, "error", reason="native_status_invalid", request_id=request_id)
    if completed.returncode != EXIT_CODES[payload["status"]]:
        return None, result(operation, "error", reason="native_exit_status_mismatch", request_id=request_id)
    return payload, None


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
    gate = _runtime_gate(operation, request_id)
    if gate:
        return gate
    payload, failure = _invoke(["get", setting], operation, request_id)
    if failure:
        return failure
    if payload.get("status") != "verified":
        return result(operation, payload["status"], data=payload, reason=payload.get("reason"),
                      request_id=request_id, complete=False)
    value = payload.get("value")
    if not _number(value) or not 0.0 <= value <= 1.0:
        return result(operation, "error", reason="native_value_invalid", request_id=request_id)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
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
    if not _number(value) or not 0.0 <= value <= 1.0:
        return result(operation, "error", reason="invalid_value", request_id=request_id)
    gate = _runtime_gate(operation, request_id)
    if gate:
        return gate
    payload, failure = _invoke(["set", setting, format(float(value), ".9f")], operation, request_id)
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
    if abs(readback - requested) > VOLUME_TOLERANCE + 1e-9:
        return result(operation, "partial", data=payload, reason="readback_mismatch",
                      request_id=request_id, complete=False)
    return result(operation, "verified", data=payload, source=NATIVE_SOURCE,
                  request_id=request_id, complete=True)


def get_setting(params, request_id=None):
    return _get(params, request_id)


def set_setting(params, request_id=None):
    return _set(params, request_id)
