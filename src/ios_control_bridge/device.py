"""Read actual iOS identity without assuming that the caller runs on a phone."""
from pathlib import Path
import os
import plistlib
import shutil
import subprocess
import sys

from .result import result

SYSTEM_VERSION = Path("/System/Library/CoreServices/SystemVersion.plist")


def ios_version(path=None):
    path = Path(path) if path is not None else SYSTEM_VERSION
    if sys.platform != "darwin" or not path.is_file():
        return None
    try:
        with path.open("rb") as stream:
            value = plistlib.load(stream)
    except (OSError, ValueError, plistlib.InvalidFileException):
        return None
    if value.get("ProductName") not in ("iPhone OS", "iOS", "iPadOS"):
        return None
    return value


def device_info(request_id=None):
    version = ios_version()
    if version is None:
        return result("device.info", "unavailable", reason="not_ios", request_id=request_id)
    data = {
        "os_version": version.get("ProductVersion"),
        "os_build": version.get("ProductBuildVersion"),
        "product_name": version.get("ProductName"),
        "uid": os.geteuid(),
        "bootstrap_prefix": "/var/jb" if Path("/var/jb").is_dir() else None,
        "model": None,
    }
    sysctl = shutil.which("sysctl")
    if sysctl:
        try:
            model = subprocess.run([sysctl, "-n", "hw.machine"], capture_output=True,
                                   text=True, timeout=2, check=False)
            if model.returncode == 0 and 0 < len(model.stdout.strip()) < 100:
                data["model"] = model.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    complete = data["model"] is not None
    return result("device.info", "verified" if complete else "partial", data=data,
                  source="SystemVersion.plist+sysctl" if complete else "SystemVersion.plist",
                  reason=None if complete else "model_unavailable", request_id=request_id, complete=complete)
