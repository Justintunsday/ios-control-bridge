"""Optional OpenCode adapter for native Siri; independent of the iosctl core."""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

PROTOCOL = "ios-control-bridge.siri.v1"
MAX_QUERY = 4096


class BackendError(Exception):
    def __init__(self, reason, ambiguous=False):
        super().__init__(reason)
        self.reason, self.ambiguous = reason, ambiguous


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OpenCodeHTTP:
    def __init__(self, origin, password, username="opencode"):
        parsed = urllib.parse.urlsplit(origin)
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1")
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/")):
            raise ValueError("Siri backend requires a loopback OpenCode origin")
        self.origin = origin.rstrip("/")
        self.authorization = "Basic " + base64.b64encode((username + ":" + password).encode()).decode()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def call(self, method, path, body=None, timeout=6):
        if not path.startswith("/api/"):
            raise ValueError("invalid OpenCode API path")
        data = None if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        request = urllib.request.Request(self.origin + path, data=data, method=method,
            headers={"Authorization": self.authorization, "Accept": "application/json",
                     "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read(12 * 1024 * 1024 + 1)
                if len(raw) > 12 * 1024 * 1024:
                    raise BackendError("response_too_large", ambiguous=method == "POST")
                result = json.loads(raw) if raw else {}
                if not isinstance(result, dict):
                    raise BackendError("invalid_response", ambiguous=method == "POST")
                return result
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            raise BackendError("http_" + str(code), ambiguous=method == "POST" and not 400 <= code < 500) from None
        except (OSError, ValueError, urllib.error.URLError) as error:
            raise BackendError("transport_unavailable", ambiguous=method == "POST") from error


def spoken_text(value):
    value = re.sub(r"```[\s\S]*?```", "代码请在 App 中查看。", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"(?m)^#{1,6}\s+", "", value)
    value = value.replace("**", "").replace("`", "").strip()
    return value[:1600] + ("。完整内容可在 BridgeChat 查看。" if len(value) > 1600 else "")


def assistant_text(message):
    if not isinstance(message, dict) or message.get("type") != "assistant":
        return ""
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    return "\n".join(part["text"] for part in content
        if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)).strip()


class SiriBackend:
    def __init__(self, http, state_file, *, model=None, project_directory=None,
                 unlocked=lambda: False, wait_seconds=20, poll_seconds=.5):
        if not math.isfinite(wait_seconds) or not 0 < wait_seconds <= 60:
            raise ValueError("wait_seconds must be within 0..60")
        self.http, self.state_file = http, Path(state_file)
        self.model, self.project_directory, self.unlocked = model, project_directory, unlocked
        self.wait_seconds, self.poll_seconds = wait_seconds, poll_seconds
        self.lock = threading.Lock()
        self.deadline = 0
        self.state = json.loads(self.state_file.read_text()) if self.state_file.exists() else {"requests": {}}
        if not isinstance(self.state, dict) or not isinstance(self.state.get("requests"), dict):
            raise ValueError("invalid Siri state file")

    def _save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.state_file.with_name(self.state_file.name + ".tmp-" + uuid.uuid4().hex)
        fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf8") as stream:
            json.dump(self.state, stream, ensure_ascii=False, allow_nan=False)
        os.replace(temporary, self.state_file)

    @staticmethod
    def reply(ident, status, text, **metadata):
        return {"protocol": PROTOCOL, "id": ident, "status": status, "text": text, **metadata}

    def _call(self, method, path, body=None):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise BackendError("deadline_exceeded")
        return self.http.call(method, path, body, timeout=min(6, remaining))

    def _object(self, path):
        result = self._call("GET", path).get("data")
        if not isinstance(result, dict):
            raise BackendError("invalid_response")
        return result

    def _messages(self, path):
        result = self._call("GET", path + "/message?limit=30&order=desc").get("data")
        if not isinstance(result, list) or any(not isinstance(row, dict) for row in result):
            raise BackendError("invalid_response")
        return result

    @staticmethod
    def _stamp(info):
        raw = info.get("time")
        if not isinstance(raw, dict):
            raise BackendError("invalid_response")
        stamp = {key: raw.get(key, 0) for key in ("busy", "idle")}
        if any(not isinstance(stamp[key], (int, float)) or not math.isfinite(stamp[key]) for key in stamp):
            raise BackendError("invalid_response")
        return stamp

    def handle(self, request):
        if not isinstance(request, dict) or request.get("protocol") != PROTOCOL:
            return self.reply(None, "error", "语音接口请求无效。", reason="invalid_protocol")
        try:
            ident = str(uuid.UUID(request.get("id", "")))
        except (ValueError, AttributeError, TypeError):
            return self.reply(None, "error", "语音接口请求无效。", reason="invalid_id")
        if request.get("op") == "status":
            return self.reply(ident, "ready", "OpenCode 语音入口已就绪。", unlocked=bool(self.unlocked()))
        value = request.get("text")
        if (request.get("op") != "ask" or set(request) - {"protocol", "id", "op", "text"}
                or not isinstance(value, str) or not value.strip() or len(value) > MAX_QUERY):
            return self.reply(ident, "error", "这句话过长或请求格式不正确。", reason="invalid_request")
        try:
            value.encode("utf8")
        except UnicodeError:
            return self.reply(ident, "error", "语音文字编码无效。", reason="invalid_unicode")
        if not self.unlocked():
            return self.reply(ident, "locked", "请先解锁手机，再与 OpenCode 对话。")
        if not self.lock.acquire(blocking=False):
            return self.reply(ident, "busy", "上一条请求仍在处理中，请稍候。")
        try:
            self.deadline = time.monotonic() + 36
            return self._ask(ident, value.strip())
        except BackendError as error:
            return self.reply(ident, "unavailable", "暂时无法确认 OpenCode 的处理结果，请在 BridgeChat 查看；这条请求不会自动重发。",
                              reason=error.reason, outcome_unknown=error.ambiguous)
        finally:
            self.lock.release()

    def _session(self):
        session = self.state.get("session_id")
        if session:
            return session
        body = {"title": "Siri · OpenCode", "agent": "build", "metadata": {"client": "siri-bridge"}}
        if self.model:
            body["model"] = self.model
        if self.project_directory:
            body["location"] = {"directory": self.project_directory}
        result = self._call("POST", "/api/session", body).get("data")
        session = result.get("id") if isinstance(result, dict) else None
        if not isinstance(session, str) or not re.fullmatch(r"ses[A-Za-z0-9_-]{1,180}", session):
            raise BackendError("invalid_session")
        self.state["session_id"] = session
        self._save()
        return session

    def _ask(self, ident, value):
        path = "/api/session/" + self._session()
        previous = self.state["requests"].get(ident)
        if previous is not None:
            if previous.get("query_sha256") != hashlib.sha256(value.encode()).hexdigest():
                return self.reply(ident, "error", "请求标识已用于另一句话。", reason="request_id_reused")
            if previous.get("phase") == "submitting":
                return self.reply(ident, "pending", "这条请求的状态仍待确认，请在 BridgeChat 查看。", outcome_unknown=True)
            if previous.get("phase") == "rejected":
                return self.reply(ident, "error", "这条请求未被 OpenCode 接受，请在 BridgeChat 检查服务。", reason="request_rejected")
            return self._poll(ident, path, previous)
        if len(self.state["requests"]) >= 64:
            finished = [key for key, item in self.state["requests"].items()
                        if item.get("phase") in ("answered", "rejected")]
            if not finished:
                return self.reply(ident, "busy", "待确认的语音请求较多，请先在 BridgeChat 查看处理结果。")
            del self.state["requests"][finished[0]]
        info = self._object(path)
        stamp = self._stamp(info)
        if stamp.get("busy", 0) > stamp.get("idle", 0):
            return self.reply(ident, "busy", "OpenCode 正在处理上一项任务，可以在 BridgeChat 查看进度。")
        messages = self._messages(path)
        entry = {"message_id": "msg_" + format(int(time.time() * 1000), "x") + uuid.UUID(ident).hex[:16],
                 "baseline": [m.get("id") for m in messages], "busy_before": stamp.get("busy", 0),
                 "query_sha256": hashlib.sha256(value.encode()).hexdigest(),
                 "phase": "submitting", "created": time.time()}
        self.state["requests"][ident] = entry
        self._save()
        instruction = (
            "你现在通过原生 Siri 与手机主人对话。默认用中文简短回答，一到三句。"
            "需要当前系统状态时使用已安装的 ios-control-bridge skill 和实际 iosctl 接口；"
            "用户明确要求修改时按准确目标执行并读回，不能把 submitted 当成已成功。"
            "只有用户明确要求观察屏幕或操作界面时才连接 iosremote；否则保持远控断开。"
            "普通界面文字优先 insert_text，不通过拼音选字。不要朗读 UUID、凭据或长日志。"
            "长任务说明真实进度，后续可在 BridgeChat 查看。以下是本次用户完整语音转写：\n\n"
        )
        try:
            self._call("POST", path + "/prompt", {"id": entry["message_id"], "text": instruction + value, "resume": True})
        except BackendError as error:
            if not error.ambiguous:
                entry["phase"] = "rejected"
                self._save()
            raise
        entry["phase"] = "accepted"
        self._save()
        return self._poll(ident, path, entry)

    def _poll(self, ident, path, entry):
        if entry.get("phase") == "answered" and entry.get("assistant_id"):
            message = self._object(path + "/message/" + entry["assistant_id"])
            value = assistant_text(message)
            if value:
                return self.reply(ident, "answered", spoken_text(value))
        deadline = min(self.deadline, time.monotonic() + self.wait_seconds)
        while time.monotonic() < deadline:
            if not self.unlocked():
                return self.reply(ident, "locked", "手机已锁定。请解锁后在 BridgeChat 查看处理结果。")
            info = self._object(path)
            rows = self._messages(path)
            stamp = self._stamp(info)
            cycle_started = stamp.get("busy", 0) > entry.get("busy_before", 0)
            active = stamp.get("busy", 0) > stamp.get("idle", 0)
            fresh = [m for m in rows if m.get("id") not in entry.get("baseline", []) and m.get("type") == "assistant"]
            if cycle_started and not active:
                if info.get("outcome") not in (None, "succeeded") or any(m.get("error") for m in fresh):
                    return self.reply(ident, "error", "OpenCode 未能完成这次请求，请在 BridgeChat 查看具体原因。", reason="agent_failed")
                for message in fresh:
                    value = assistant_text(message)
                    if value:
                        entry.update(phase="answered", assistant_id=message["id"])
                        self._save()
                        return self.reply(ident, "answered", spoken_text(value))
            time.sleep(min(self.poll_seconds, max(0, deadline - time.monotonic())))
        return self.reply(ident, "pending", "OpenCode 仍在处理，可以在 BridgeChat 继续查看。", accepted=True)
