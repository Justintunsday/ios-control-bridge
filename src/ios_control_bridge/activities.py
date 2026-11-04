"""Invoke the version-gated native reader, keeping errors and empty results distinct."""
from pathlib import Path
import json
import os
import subprocess
import time
from uuid import UUID

from .device import ios_version
from .result import EXIT_CODES, result

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NATIVE_SCHEMA = "activity-private-content-v1"
NATIVE_SOURCE = "sessionkitd-activitykit-private-output"


def helper_path():
    configured = os.environ.get("ICB_ACTIVITIES_HELPER")
    return Path(configured).expanduser() if configured else PROJECT_ROOT / "build/native/icb-activities"


def get_activity(params, request_id=None):
    operation = "activities.get"
    extra = set(params) - {"activity_id", "timeout_ms", "diagnostics"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    try:
        identifier = str(UUID(params["activity_id"])).upper()
    except (KeyError, TypeError, ValueError, AttributeError):
        return result(operation, "error", reason="invalid_activity_id", request_id=request_id)
    timeout_ms = params.get("timeout_ms", 5000)
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 15000:
        return result(operation, "error", reason="invalid_timeout_ms", request_id=request_id)
    diagnostics = params.get("diagnostics", False)
    if type(diagnostics) is not bool:
        return result(operation, "error", reason="invalid_diagnostics", request_id=request_id)
    version = ios_version()
    if version is None:
        return result(operation, "unavailable", reason="not_ios", request_id=request_id)
    if (version.get("ProductVersion"), version.get("ProductBuildVersion")) != ("16.1.1", "20B101"):
        return result(operation, "unavailable", reason="unverified_os_build", request_id=request_id)
    binary = helper_path()
    if not binary.is_file():
        return result(operation, "unavailable", reason="native_helper_missing", request_id=request_id)
    args = [str(binary), "--activity-id", identifier, "--timeout-ms", str(timeout_ms)]
    if diagnostics:
        args.append("--diagnostics")
    try:
        completed = subprocess.run(args, capture_output=True, text=True,
                                   timeout=timeout_ms / 1000 + 2, check=False)
    except subprocess.TimeoutExpired:
        return result(operation, "unavailable", reason="native_process_timeout", request_id=request_id)
    except OSError:
        return result(operation, "unavailable", reason="native_process_unavailable", request_id=request_id)
    if len(completed.stdout.encode("utf8")) > 524288:
        return result(operation, "partial", reason="native_output_limit", request_id=request_id)
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, ValueError):
        return result(operation, "error", reason="invalid_native_json", request_id=request_id)
    if not isinstance(payload, dict) or payload.get("schema") != NATIVE_SCHEMA:
        return result(operation, "error", reason="native_schema_mismatch", request_id=request_id)
    status = payload.get("status")
    if status not in EXIT_CODES or completed.returncode != EXIT_CODES[status]:
        return result(operation, "error", reason="native_exit_status_mismatch", request_id=request_id)
    if payload.get("source") != NATIVE_SOURCE:
        return result(operation, "error", reason="native_source_mismatch", request_id=request_id)
    if payload.get("requested_activity_id") != identifier:
        return result(operation, "error", reason="native_target_mismatch", request_id=request_id)
    if status == "verified" and (payload.get("complete_for_scope") is not True
                                 or type(payload.get("target_found")) is not bool):
        return result(operation, "error", reason="incomplete_native_success", request_id=request_id)
    if status == "verified":
        if payload["target_found"]:
            activity = payload.get("activity")
            descriptor = activity.get("descriptor") if isinstance(activity, dict) else None
            if not isinstance(descriptor, dict) or descriptor.get("id") != identifier or "content" not in payload:
                return result(operation, "error", reason="native_activity_inconsistent", request_id=request_id)
        elif payload.get("activity") is not None or "activity" not in payload or "content" in payload:
            return result(operation, "error", reason="native_activity_inconsistent", request_id=request_id)
    return result(operation, status, data=payload, reason=payload.get("reason"),
                  source=NATIVE_SOURCE, request_id=request_id,
                  complete=status == "verified" and payload.get("complete_for_scope") is True)


WATCH_DEFAULT_DURATION_MS = 5000
WATCH_DEFAULT_INTERVAL_MS = 1000
WATCH_DEFAULT_TIMEOUT_MS = 3000


def _activity_state(data):
    activity = data.get("activity") if isinstance(data, dict) else None
    if not isinstance(activity, dict):
        return None
    state = activity.get("state")
    return state if isinstance(state, dict) else None


def watch_activity(params, request_id=None):
    operation = "activities.watch"
    extra = set(params) - {"activity_id", "duration_ms", "interval_ms", "timeout_ms", "stop_on_change"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    try:
        identifier = str(UUID(params["activity_id"])).upper()
    except (KeyError, TypeError, ValueError, AttributeError):
        return result(operation, "error", reason="invalid_activity_id", request_id=request_id)
    duration_ms = params.get("duration_ms", WATCH_DEFAULT_DURATION_MS)
    if type(duration_ms) is not int or not 1000 <= duration_ms <= 30000:
        return result(operation, "error", reason="invalid_duration_ms", request_id=request_id)
    interval_ms = params.get("interval_ms", WATCH_DEFAULT_INTERVAL_MS)
    if type(interval_ms) is not int or not 500 <= interval_ms <= 5000:
        return result(operation, "error", reason="invalid_interval_ms", request_id=request_id)
    timeout_ms = params.get("timeout_ms", WATCH_DEFAULT_TIMEOUT_MS)
    if type(timeout_ms) is not int or not 500 <= timeout_ms <= 5000:
        return result(operation, "error", reason="invalid_timeout_ms", request_id=request_id)
    stop_on_change = params.get("stop_on_change", False)
    if type(stop_on_change) is not bool:
        return result(operation, "error", reason="invalid_stop_on_change", request_id=request_id)
    version = ios_version()
    if version is None:
        return result(operation, "unavailable", reason="not_ios", request_id=request_id)
    if (version.get("ProductVersion"), version.get("ProductBuildVersion")) != ("16.1.1", "20B101"):
        return result(operation, "unavailable", reason="unverified_os_build", request_id=request_id)
    if not helper_path().is_file():
        return result(operation, "unavailable", reason="native_helper_missing", request_id=request_id)

    deadline = time.monotonic() + duration_ms / 1000.0
    samples = []
    changes = 0
    previous_state = None
    stopped_early = False
    target_found_ever = False
    while True:
        probe = get_activity({"activity_id": identifier, "timeout_ms": timeout_ms}, request_id=request_id)
        if probe.get("status") != "verified":
            return result(operation, probe.get("status", "error"), reason=probe.get("reason"),
                          data={"activity_id": identifier, "samples": samples,
                                "failed_probe": probe.get("request_id")},
                          request_id=request_id)
        payload = probe.get("data") or {}
        target_found = payload.get("target_found") is True
        target_found_ever = target_found_ever or target_found
        state = _activity_state(payload) if target_found else None
        samples.append({"observed_at": probe.get("observed_at"), "target_found": target_found,
                        "state": state})
        if previous_state is not None and state != previous_state:
            changes += 1
            if stop_on_change:
                stopped_early = True
                break
        previous_state = state
        if time.monotonic() >= deadline:
            break
        time.sleep(interval_ms / 1000.0)
    complete = not stopped_early
    return result(operation, "verified", request_id=request_id, complete=complete,
                  data={"activity_id": identifier, "duration_ms": duration_ms,
                        "interval_ms": interval_ms, "timeout_ms": timeout_ms,
                        "stop_on_change": stop_on_change, "stopped_early": stopped_early,
                        "changed": changes > 0, "changes": changes,
                        "target_found_ever": target_found_ever, "samples": samples},
                  source=NATIVE_SOURCE)
