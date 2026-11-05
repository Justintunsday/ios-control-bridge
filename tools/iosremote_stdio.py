"""Small MCP stdio transport for the Python 3.9 iOS host; no third-party SDK.

Device authentication and input still use the reviewed iOSRemoteBridge client.
This server implements only initialization, ping and the advertised tools.
"""
import argparse
import base64
import json
import math
import sys

VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
MAX_LINE = 65536
COORD = {"type": "number", "minimum": 0, "maximum": 1}
DURATION = {"type": "integer", "minimum": 40, "maximum": 5000, "default": 400}


def tool(name, description, properties=None, required=None, read=True):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties or {},
                            "required": required or [], "additionalProperties": False},
            "annotations": {"readOnlyHint": read, "destructiveHint": not read,
                            "idempotentHint": read or name == "disconnect",
                            "openWorldHint": not read and name != "disconnect"}}


TOOLS = [
    tool("get_device_info", "Read actual model, iOS, lock state and input readiness."),
    tool("get_screen_frame", "View a current JPEG screen image before selecting an action."),
    tool("get_orientation", "Read natural-portrait capture dimensions and orientation."),
    tool("get_connection_status", "Read this adapter's status without connecting to the phone."),
    tool("tap", "Tap a point observed in the latest image; inspect a fresh image afterwards.",
         {"x": COORD, "y": COORD}, ["x", "y"], False),
    tool("swipe", "Swipe in normalized natural-portrait coordinates; then inspect a fresh image.",
         {"x": COORD, "y": COORD, "to_x": COORD, "to_y": COORD, "duration_ms": DURATION},
         ["x", "y", "to_x", "to_y"], False),
    tool("type_text", "Type at most 1024 US-layout ASCII characters into an observed focused field.",
         {"text": {"type": "string", "maxLength": 1024}}, ["text"], False),
    tool("press_home", "Press Home, then inspect the resulting screen.", read=False),
    tool("disconnect", "Release this adapter's device session.", read=False),
]
CATALOG = {t["name"]: t for t in TOOLS}


def validate(name, arguments):
    if name not in CATALOG:
        raise ValueError("unknown tool")
    schema = CATALOG[name]["inputSchema"]
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    if set(arguments) - set(schema["properties"]):
        raise ValueError("unknown tool argument")
    if set(schema["required"]) - set(arguments):
        raise ValueError("missing tool argument")
    result = dict(arguments)
    for key, spec in schema["properties"].items():
        if key not in result:
            if "default" in spec:
                result[key] = spec["default"]
            continue
        value = result[key]
        kind = spec["type"]
        if kind in ("number", "integer"):
            if type(value) not in (int, float) or (kind == "integer" and type(value) is not int):
                raise ValueError(key + " must be a " + kind)
            if not math.isfinite(value) or not spec["minimum"] <= value <= spec["maximum"]:
                raise ValueError(key + " is outside its allowed range")
        elif kind == "string":
            if not isinstance(value, str) or len(value) > spec["maxLength"]:
                raise ValueError(key + " must be a bounded string")
            if name == "type_text" and not value.isascii():
                raise ValueError("type_text supports US-layout ASCII only")
    return result


class Adapter:
    def __init__(self, config, control=False, factory=None):
        self.config, self.control, self.factory = config, control, factory
        self.client = None

    def close(self):
        client, self.client = self.client, None
        if client is not None:
            client.close()

    def call(self, name, arguments):
        arguments = validate(name, arguments)
        if name == "disconnect":
            self.close()
            return {"connected": False}
        if name == "get_connection_status":
            return {"connected": self.client is not None and not self.client.error,
                    "input_requested": self.control}
        if not CATALOG[name]["annotations"]["readOnlyHint"] and not self.control:
            raise ValueError("input disabled; this adapter requires --control")
        if self.client is None:
            factory = self.factory
            if factory is None:
                from automation import BridgeClient
                factory = BridgeClient
            self.client = factory(self.config, control=self.control, timeout=20)
            try:
                self.client.connect()
            except Exception:
                self.close()
                raise
        try:
            return self.client.request(name, **arguments)
        except Exception:
            if self.client.error:
                self.close()
            raise  # Never replay a failed input operation.


class Server:
    def __init__(self, adapter):
        self.adapter = adapter
        self.initialized = False
        self.ready = False

    @staticmethod
    def error(ident, code, message):
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}}

    def dispatch(self, request):
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return self.error(None, -32600, "invalid request")
        ident = request.get("id")
        method = request.get("method")
        if "id" not in request:
            if method == "notifications/initialized" and self.initialized:
                self.ready = True
            return None
        if type(ident) not in (int, str) or not isinstance(method, str):
            return self.error(None, -32600, "invalid request id or method")
        params = request.get("params", {})
        if not isinstance(params, dict):
            return self.error(ident, -32602, "params must be an object")
        if method == "initialize":
            if self.initialized or not isinstance(params.get("protocolVersion"), str):
                return self.error(ident, -32602, "invalid initialization")
            self.initialized = True
            version = params["protocolVersion"]
            result = {"protocolVersion": version if version in VERSIONS else "2025-11-25",
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "iosremote-python39", "version": "1.0.0"}}
        elif method == "ping":
            result = {}
        elif not self.ready:
            return self.error(ident, -32000, "initialize this MCP session first")
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            try:
                name = params.get("name")
                if not isinstance(name, str):
                    raise ValueError("tool name must be a string")
                value = self.adapter.call(name, params.get("arguments", {}))
                if name == "get_screen_frame":
                    if value.get("mime") != "image/jpeg":
                        raise ValueError("unexpected image type")
                    encoded = value["base64"]
                    if not isinstance(encoded, str) or len(encoded) > 2000000:
                        raise ValueError("screen image exceeds response limit")
                    base64.b64decode(encoded, validate=True)
                    content = [{"type": "image", "mimeType": "image/jpeg", "data": encoded}]
                else:
                    content = [{"type": "text", "text": json.dumps(value, ensure_ascii=False, allow_nan=False)}]
                result = {"content": content, "isError": False}
            except Exception as exc:
                result = {"content": [{"type": "text", "text": str(exc)[:800]}], "isError": True}
        else:
            return self.error(ident, -32601, "method not found")
        return {"jsonrpc": "2.0", "id": ident, "result": result}

    def serve(self, input_stream, output_stream):
        try:
            while True:
                raw = input_stream.readline(MAX_LINE + 1)
                if not raw:
                    break
                if len(raw) > MAX_LINE:
                    response = self.error(None, -32600, "request exceeds line limit")
                else:
                    try:
                        response = self.dispatch(json.loads(raw))
                    except (ValueError, UnicodeError):
                        response = self.error(None, -32700, "invalid JSON")
                if response is not None:
                    line = json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n"
                    output_stream.write(line.encode("utf8"))
                    output_stream.flush()
                if len(raw) > MAX_LINE:
                    break
        finally:
            self.adapter.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--control", action="store_true")
    args = parser.parse_args()
    Server(Adapter(args.config, args.control)).serve(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    main()
