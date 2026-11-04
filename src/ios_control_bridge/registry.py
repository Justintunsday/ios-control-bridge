"""Declare project scope separately from implemented and device-verified adapters."""
from dataclasses import asdict, dataclass

from .activities import get_activity, helper_path as activities_helper_path
from .device import device_info, ios_version
from .result import result
from .settings import (SUPPORTED_SETTINGS, get_setting, helper_path as settings_helper_path,
                       set_setting)


@dataclass(frozen=True)
class Operation:
    name: str
    summary: str
    mutates: bool = False
    implemented: bool = False
    validation: str = "planned"


OPERATIONS = [
    Operation("device.info", "Read OS build, model, UID and bootstrap evidence", implemented=True, validation="device_verified"),
    Operation("activities.get", "Read a selected Live Activity's raw content and state", implemented=True, validation="device_verified"),
    Operation("activities.watch", "Monitor activity changes until an explicit stop condition"),
    Operation("settings.get", "Read a supported setting (currently volume)", implemented=True, validation="device_verified"),
    Operation("settings.set", "Change a supported setting and verify the readback (currently volume)", mutates=True, implemented=True, validation="device_verified"),
    Operation("alarms.list", "Read system alarms"),
    Operation("alarms.create", "Create an alarm with explicit time, timezone and repetition", mutates=True),
    Operation("alarms.update", "Modify one alarm by stable ID", mutates=True),
    Operation("alarms.set_enabled", "Enable or disable one alarm", mutates=True),
    Operation("alarms.delete", "Delete one identified alarm", mutates=True),
    Operation("reminders.lists", "Read reminder lists"),
    Operation("reminders.list", "Read reminders within a selected list and time range"),
    Operation("reminders.create", "Create a reminder with an explicit destination list", mutates=True),
    Operation("reminders.update", "Modify one reminder by stable ID", mutates=True),
    Operation("reminders.complete", "Mark one reminder completed or incomplete", mutates=True),
    Operation("reminders.delete", "Delete one identified reminder", mutates=True),
    Operation("browser.search", "Return web search results with titles, links and source timestamps"),
    Operation("browser.read", "Read a selected page and report extraction limits"),
    Operation("browser.open", "Open a selected HTTP(S) URL on the device", mutates=True),
    Operation("weather.current", "Query current weather for an explicit location"),
    Operation("weather.forecast", "Query forecast data and retain provider attribution"),
    Operation("files.list", "List files under an explicit directory"),
    Operation("files.search", "Search within an explicit directory with bounded results"),
    Operation("files.read", "Read a selected file with size and encoding limits"),
]
BY_NAME = {operation.name: operation for operation in OPERATIONS}

SETTINGS_BUILD = ("16.1.1", "20B101")


def _settings_readiness(version):
    if version is None:
        return False, "not_ios"
    if (version.get("ProductVersion"), version.get("ProductBuildVersion")) != SETTINGS_BUILD:
        return False, "unverified_os_build"
    if not settings_helper_path().is_file():
        return False, "native_helper_missing"
    return True, None


def catalog(service=None):
    version = ios_version()
    rows = []
    for operation in OPERATIONS:
        if service and not operation.name.startswith(service + "."):
            continue
        row = asdict(operation)
        ready = operation.implemented and version is not None
        reason = None
        if not operation.implemented:
            reason = "not_implemented"
        elif version is None:
            reason = "not_ios"
        elif operation.name == "activities.get":
            if (version.get("ProductVersion"), version.get("ProductBuildVersion")) != ("16.1.1", "20B101"):
                ready, reason = False, "unverified_os_build"
            elif not activities_helper_path().is_file():
                ready, reason = False, "native_helper_missing"
        elif operation.name.startswith("settings."):
            ready, reason = _settings_readiness(version)
        row["runtime"] = {"ready_to_query": ready, "reason": reason}
        if operation.name == "activities.get":
            row["verified_builds"] = ["20B101"] if operation.validation == "device_verified" else []
        if operation.name.startswith("settings."):
            row["supported_settings"] = list(SUPPORTED_SETTINGS)
            row["verified_builds"] = ["20B101"] if operation.validation == "device_verified" else []
        rows.append(row)
    return rows


def invoke(operation, params, request_id=None):
    definition = BY_NAME.get(operation)
    if definition is None:
        return result(operation, "error", reason="unknown_operation", request_id=request_id)
    if not isinstance(params, dict):
        return result(operation, "error", reason="parameters_must_be_object", request_id=request_id)
    if not definition.implemented:
        return result(operation, "unavailable", reason="not_implemented",
                      data={"implemented": False, "mutates": definition.mutates}, request_id=request_id)
    if operation == "activities.get":
        return get_activity(params, request_id)
    if operation == "device.info":
        if params:
            return result(operation, "error", reason="unknown_parameters", request_id=request_id)
        return device_info(request_id)
    if operation == "settings.get":
        return get_setting(params, request_id)
    if operation == "settings.set":
        return set_setting(params, request_id)
    return result(operation, "unavailable", reason="adapter_missing", request_id=request_id)
