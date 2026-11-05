"""On-device, peer-authenticated Unix socket entry point for native Siri."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import socket
import socketserver
import stat
import struct
import sys
import threading

if __package__:
    from .backend import OpenCodeHTTP, SiriBackend
else:
    from backend import OpenCodeHTTP, SiriBackend

MAX_FRAME = 65536


def private_bytes(path, maximum):
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077 or not 0 < info.st_size <= maximum):
            raise ValueError("private file permissions or size are invalid")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            return stream.read(maximum + 1)
    finally:
        os.close(fd)


class DarwinState:
    def __init__(self):
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.libc.sysctlbyname.argtypes = [ctypes.c_char_p, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p, ctypes.c_size_t]
        self.libc.sysctlbyname.restype = ctypes.c_int
        build = ctypes.create_string_buffer(64)
        length = ctypes.c_size_t(len(build))
        if self.libc.sysctlbyname(b"kern.osversion", build, ctypes.byref(length), None, 0) or build.value != b"20B101":
            raise RuntimeError("native Siri backend is verified only on iOS build 20B101")
        # launchd's default 18 MiB daemon limit kills Python on its first HTTP call.
        # Set/read back this process's bounded limit, never another service's limit.
        class Limits(ctypes.Structure):
            _fields_ = [("active", ctypes.c_int32), ("active_attributes", ctypes.c_uint32),
                        ("inactive", ctypes.c_int32), ("inactive_attributes", ctypes.c_uint32)]
        self.libc.memorystatus_control.argtypes = [ctypes.c_uint32, ctypes.c_int32,
            ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t]
        self.libc.memorystatus_control.restype = ctypes.c_int
        limits = Limits(128, 1, 128, 1)
        if self.libc.memorystatus_control(7, os.getpid(), 0, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise OSError(ctypes.get_errno(), "cannot configure Siri backend memory limit")
        observed = Limits()
        if (self.libc.memorystatus_control(8, os.getpid(), 0, ctypes.byref(observed), ctypes.sizeof(observed))
                or observed.active != 128 or observed.inactive != 128):
            raise RuntimeError("Siri backend memory limit readback failed")
        self.token = ctypes.c_int(-1)
        self.libc.notify_register_check.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
        self.libc.notify_register_check.restype = ctypes.c_uint32
        self.libc.notify_get_state.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint64)]
        self.libc.notify_get_state.restype = ctypes.c_uint32
        self.libc.getpeereid.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
        self.libc.getpeereid.restype = ctypes.c_int
        self.registered = self.libc.notify_register_check(b"com.apple.springboard.lockstate", ctypes.byref(self.token)) == 0

    def unlocked(self):
        value = ctypes.c_uint64(1)
        return (self.registered and self.libc.notify_get_state(self.token.value, ctypes.byref(value)) == 0
                and value.value == 0)

    def peer_uid(self, connection):
        user, group = ctypes.c_uint(), ctypes.c_uint()
        if self.libc.getpeereid(connection.fileno(), ctypes.byref(user), ctypes.byref(group)):
            raise OSError("peer authentication failed")
        return user.value


def receive_exact(connection, length):
    result = bytearray()
    while len(result) < length:
        chunk = connection.recv(length - len(result))
        if not chunk:
            raise EOFError("incomplete Siri frame")
        result.extend(chunk)
    return bytes(result)


def receive(connection):
    length = struct.unpack("!I", receive_exact(connection, 4))[0]
    if not 0 < length <= MAX_FRAME:
        raise ValueError("Siri frame exceeds limit")
    return json.loads(receive_exact(connection, length).decode("utf8"))


def send(connection, result):
    body = json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf8")
    if len(body) > MAX_FRAME:
        raise ValueError("Siri reply exceeds limit")
    connection.sendall(struct.pack("!I", len(body)) + body)


class SiriServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    address_family = getattr(socket, "AF_UNIX", None)
    daemon_threads = True
    request_queue_size = 4

    def __init__(self, address, backend, state, mobile_uid):
        self.backend, self.state, self.mobile_uid = backend, state, mobile_uid
        self.slots = threading.BoundedSemaphore(4)
        super().__init__(str(address), SiriHandler)


class SiriHandler(socketserver.BaseRequestHandler):
    def handle(self):
        connection = self.request
        connection.settimeout(35)
        if not self.server.slots.acquire(blocking=False):
            return
        try:
            if self.server.state.peer_uid(connection) not in (0, self.server.mobile_uid):
                return
            request = receive(connection)
            result = self.server.backend.handle(request)
            send(connection, result)
        except (OSError, ValueError, TypeError, EOFError):
            return
        finally:
            self.server.slots.release()


def main():
    import fcntl
    import pwd
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin" or os.geteuid() != 0:
        raise SystemExit("native Siri service requires root on the verified iOS device")
    config = json.loads(private_bytes(args.config, 16384))
    password = private_bytes(Path(config["password_file"]), 4096).decode().strip()
    directory = Path(config["socket_directory"])
    mobile = pwd.getpwnam("mobile")
    info = directory.lstat()
    if (directory.is_symlink() or not stat.S_ISDIR(info.st_mode) or info.st_uid != mobile.pw_uid
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise SystemExit("Siri socket directory must be a mobile-owned private directory")
    state_file = Path(config["state_file"])
    state_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = os.open(str(state_file.with_suffix(".lock")), os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    endpoint = directory / "bridge.sock"
    if endpoint.exists() or endpoint.is_symlink():
        old = endpoint.lstat()
        if not stat.S_ISSOCK(old.st_mode) or old.st_uid != mobile.pw_uid:
            raise SystemExit("pre-existing Siri endpoint was preserved")
        endpoint.unlink()
    state = DarwinState()
    backend = SiriBackend(OpenCodeHTTP(config["origin"], password), state_file,
        model=config.get("model"), project_directory=config.get("project_directory"),
        unlocked=state.unlocked, wait_seconds=config.get("wait_seconds", 20))
    with SiriServer(endpoint, backend, state, mobile.pw_uid) as server:
        os.chmod(endpoint, 0o600)
        os.chown(endpoint, mobile.pw_uid, mobile.pw_gid)
        print("Siri local bridge ready", flush=True)
        try:
            server.serve_forever(poll_interval=.5)
        finally:
            endpoint.unlink(missing_ok=True)
            os.close(lock)


if __name__ == "__main__":
    main()
