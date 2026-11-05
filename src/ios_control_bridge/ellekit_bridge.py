"""Bounded, peer-authenticated local IPC; no persistent command mailbox."""
from pathlib import Path
import ctypes
import math
import os
import socket
import stat
import sys
import time
import uuid

DIRECTORY = Path(os.environ.get("ICB_ELLEKIT_DIR", "/var/jb/var/run/ios-control-bridge"))
SOCKET_PATH = DIRECTORY / "spring.sock"
BRIDGE_DYLIB = Path("/var/jb/usr/lib/TweakInject/icbridge.dylib")
PROTOCOL = "ios-control-bridge.spring.v2"
ALLOWED_ACTIONS = {"get_low_power", "set_low_power", "get_orientation_lock",
                   "set_orientation_lock", "get_wifi", "get_airplane", "get_bluetooth"}
DEFAULT_TIMEOUT = 6.0
MAX_MESSAGE = 4096


def _endpoint_owner():
    try:
        import pwd
        return pwd.getpwnam("mobile").pw_uid
    except (ImportError, KeyError):
        return None


def _secure_endpoint():
    owner = _endpoint_owner()
    if owner is None:
        return None
    try:
        directory = DIRECTORY.lstat()
        endpoint = SOCKET_PATH.lstat()
    except OSError:
        return None
    if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != owner
            or stat.S_IMODE(directory.st_mode) != 0o700
            or not stat.S_ISSOCK(endpoint.st_mode) or endpoint.st_uid != owner
            or stat.S_IMODE(endpoint.st_mode) != 0o600):
        return None
    return owner


def _peer_uid(stream):
    if sys.platform != "darwin":
        raise OSError("peer authentication requires Darwin")
    libc = ctypes.CDLL(None, use_errno=True)
    getpeereid = libc.getpeereid
    getpeereid.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
    getpeereid.restype = ctypes.c_int
    user, group = ctypes.c_uint(), ctypes.c_uint()
    if getpeereid(stream.fileno(), ctypes.byref(user), ctypes.byref(group)) != 0:
        raise OSError(ctypes.get_errno(), "getpeereid failed")
    return user.value


def available():
    return BRIDGE_DYLIB.is_file() and _secure_endpoint() is not None


def _receive(stream, deadline):
    body = bytearray()
    while len(body) <= MAX_MESSAGE:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        stream.settimeout(remaining)
        part = stream.recv(1)
        if not part:
            raise OSError("bridge disconnected")
        if part == b"\n":
            return body.decode("ascii").split()
        body.extend(part)
    raise ValueError("bridge message too large")


def request(action, value=0, timeout=DEFAULT_TIMEOUT):
    if action not in ALLOWED_ACTIONS:
        return {"status": "error", "detail": "unsupported_action"}
    if (type(timeout) not in (float, int) or not math.isfinite(timeout)
            or not 0 < timeout <= DEFAULT_TIMEOUT or type(value) not in (int, bool)
            or value not in (0, 1)):
        return {"status": "error", "detail": "invalid_request"}
    owner = _secure_endpoint()
    if owner is None:
        return {"status": "unavailable", "detail": "bridge_endpoint_unavailable"}
    if not hasattr(socket, "AF_UNIX"):
        return {"status": "unavailable", "detail": "bridge_transport_unavailable"}
    request_id = uuid.uuid4().hex
    deadline = time.monotonic() + timeout
    expires = int((time.time() + timeout) * 1000)
    sent = False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
            stream.settimeout(timeout)
            stream.connect(str(SOCKET_PATH))
            if _peer_uid(stream) != owner:
                return {"status": "error", "detail": "bridge_peer_rejected"}
            hello = _receive(stream, deadline)
            if len(hello) != 2 or hello[0] != PROTOCOL:
                raise ValueError("invalid handshake")
            generation = hello[1]
            uuid.UUID(generation)
            if len(generation) != 32:
                raise ValueError("invalid generation")
            if time.monotonic() >= deadline:
                raise TimeoutError()
            body = "%s %s %d %s %d\n" % (generation, request_id, expires, action, int(value))
            stream.settimeout(max(0.001, deadline - time.monotonic()))
            sent = True
            stream.sendall(body.encode("ascii"))
            fields = _receive(stream, deadline)
            if (len(fields) != 6 or fields[0] != generation or fields[1] != request_id
                    or fields[2] not in ("ok", "unavailable", "error")
                    or fields[4] not in ("0", "1") or len(fields[5]) > 254):
                raise ValueError("invalid response")
            return {"protocol": PROTOCOL, "generation": generation, "id": request_id,
                    "status": fields[2], "value": int(fields[3]), "outcome_unknown": fields[4] == "1",
                    "detail": bytes.fromhex(fields[5]).decode("utf8") if fields[5] != "-" else ""}
    except (OSError, ValueError, UnicodeError, OverflowError):
        return {"status": "unavailable", "detail": "bridge_response_unavailable",
                "request_id": request_id,
                "outcome_unknown": sent and action.startswith("set_")}
