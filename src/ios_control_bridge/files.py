"""Bounded local filesystem operations with explicit paths and result limits."""
from pathlib import Path
import os
import stat

from .result import result

DEFAULT_LIST_LIMIT = 100
DEFAULT_SEARCH_LIMIT = 50
DEFAULT_READ_BYTES = 65536
MAX_READ_BYTES = 1048576


def _path(params, key="path"):
    value = params.get(key)
    if not isinstance(value, str) or not value or not os.path.isabs(value):
        return None
    return Path(value)


def _limit(params, default, maximum):
    value = params.get("limit", default)
    if type(value) is not int or not 1 <= value <= maximum:
        return None
    return value


def _entry(path):
    try:
        information = path.lstat()
    except OSError:
        return None
    mode = information.st_mode
    if stat.S_ISDIR(mode):
        kind = "directory"
    elif stat.S_ISREG(mode):
        kind = "file"
    elif stat.S_ISLNK(mode):
        kind = "symlink"
    else:
        kind = "other"
    return {"name": path.name, "type": kind, "size": information.st_size,
            "mode": oct(stat.S_IMODE(mode)), "modified_at_unix": information.st_mtime}


def list_files(params, request_id=None):
    operation = "files.list"
    extra = set(params) - {"path", "limit", "include_hidden"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    path = _path(params)
    if path is None:
        return result(operation, "error", reason="invalid_path", request_id=request_id)
    limit = _limit(params, DEFAULT_LIST_LIMIT, 500)
    if limit is None:
        return result(operation, "error", reason="invalid_limit", request_id=request_id)
    include_hidden = params.get("include_hidden", False)
    if type(include_hidden) is not bool:
        return result(operation, "error", reason="invalid_include_hidden", request_id=request_id)
    try:
        if not path.is_dir():
            reason = "path_not_found" if not path.exists() else "not_a_directory"
            return result(operation, "unavailable", reason=reason, request_id=request_id)
        names = []
        with os.scandir(path) as entries:
            for entry in entries:
                if not include_hidden and entry.name.startswith("."):
                    continue
                item = _entry(Path(entry.path))
                if item is not None:
                    names.append(item)
    except PermissionError:
        return result(operation, "unavailable", reason="permission_denied", request_id=request_id)
    except OSError:
        return result(operation, "unavailable", reason="filesystem_error", request_id=request_id)
    names.sort(key=lambda item: (item["type"] != "directory", item["name"].lower()))
    truncated = len(names) > limit
    entries = names[:limit]
    return result(operation, "verified", request_id=request_id, complete=not truncated,
                  data={"path": str(path), "entries": entries, "count": len(entries),
                        "truncated": truncated, "limit": limit}, source="local_filesystem")


def search_files(params, request_id=None):
    operation = "files.search"
    extra = set(params) - {"path", "query", "limit", "max_depth", "include_hidden"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    path = _path(params)
    if path is None:
        return result(operation, "error", reason="invalid_path", request_id=request_id)
    query = params.get("query")
    if not isinstance(query, str) or not 1 <= len(query) <= 256:
        return result(operation, "error", reason="invalid_query", request_id=request_id)
    limit = _limit(params, DEFAULT_SEARCH_LIMIT, 200)
    if limit is None:
        return result(operation, "error", reason="invalid_limit", request_id=request_id)
    max_depth = params.get("max_depth", 3)
    if type(max_depth) is not int or not 1 <= max_depth <= 10:
        return result(operation, "error", reason="invalid_max_depth", request_id=request_id)
    include_hidden = params.get("include_hidden", False)
    if type(include_hidden) is not bool:
        return result(operation, "error", reason="invalid_include_hidden", request_id=request_id)
    try:
        if not path.is_dir():
            reason = "path_not_found" if not path.exists() else "not_a_directory"
            return result(operation, "unavailable", reason=reason, request_id=request_id)
    except PermissionError:
        return result(operation, "unavailable", reason="permission_denied", request_id=request_id)

    needle = query.casefold()
    matches = []
    scanned = 0

    def visit(directory, depth):
        nonlocal scanned
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if not include_hidden and entry.name.startswith("."):
                        continue
                    scanned += 1
                    try:
                        is_directory = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if needle in entry.name.casefold():
                        item = _entry(Path(entry.path))
                        if item is not None:
                            matches.append(item)
                            if len(matches) >= limit:
                                return True
                    if is_directory and depth < max_depth and visit(Path(entry.path), depth + 1):
                        return True
        except (PermissionError, OSError):
            return False
        return False

    try:
        visit(path, 1)
    except PermissionError:
        return result(operation, "unavailable", reason="permission_denied", request_id=request_id)
    truncated = len(matches) >= limit
    return result(operation, "verified", request_id=request_id, complete=not truncated,
                  data={"path": str(path), "query": query, "matches": matches[:limit],
                        "count": len(matches[:limit]), "scanned": scanned,
                        "truncated": truncated, "limit": limit, "max_depth": max_depth},
                  source="local_filesystem")


def read_file(params, request_id=None):
    operation = "files.read"
    extra = set(params) - {"path", "max_bytes"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    path = _path(params)
    if path is None:
        return result(operation, "error", reason="invalid_path", request_id=request_id)
    max_bytes = params.get("max_bytes", DEFAULT_READ_BYTES)
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_READ_BYTES:
        return result(operation, "error", reason="invalid_max_bytes", request_id=request_id)
    try:
        information = path.stat()
        if not stat.S_ISREG(information.st_mode):
            return result(operation, "unavailable", reason="not_a_file", request_id=request_id)
        with path.open("rb") as stream:
            data = stream.read(max_bytes)
    except FileNotFoundError:
        return result(operation, "unavailable", reason="path_not_found", request_id=request_id)
    except PermissionError:
        return result(operation, "unavailable", reason="permission_denied", request_id=request_id)
    except OSError:
        return result(operation, "unavailable", reason="filesystem_error", request_id=request_id)
    if b"\x00" in data:
        return result(operation, "unavailable", reason="binary_file", request_id=request_id)
    try:
        text = data.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
        encoding = "utf-8-replace"
    truncated = information.st_size > len(data)
    return result(operation, "verified" if not truncated else "partial",
                  request_id=request_id, complete=not truncated,
                  data={"path": str(path), "content": text, "bytes_read": len(data),
                        "size": information.st_size, "truncated": truncated,
                        "encoding": encoding, "max_bytes": max_bytes},
                  source="local_filesystem")
