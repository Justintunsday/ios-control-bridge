"""Standalone JSON CLI; no AI SDK, coding-agent server or SSH credential dependency."""
import argparse
import json
import sys
from uuid import UUID

from . import __version__
from .registry import OPERATIONS, catalog, invoke
from .result import EXIT_CODES, result


class ArgumentError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentError(message)


def parse(argv):
    parser = Parser(prog="iosctl", description="iOS Control Bridge")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    capability = commands.add_parser("capabilities", help="List implemented and planned operations")
    capability.add_argument("--service", choices=sorted({op.name.split(".")[0] for op in OPERATIONS}))
    call = commands.add_parser("call", help="Invoke one operation with JSON parameters")
    call.add_argument("operation")
    call.add_argument("--params", default="{}")
    call.add_argument("--request-id", help="Optional caller-provided UUID")
    return parser.parse_args(argv)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    operation = "cli"
    request_id = None
    try:
        args = parse(argv)
        if args.command == "capabilities":
            output = result("capabilities", "verified", data={"project": "iOS Control Bridge",
                            "version": __version__, "operations": catalog(args.service)},
                            source="declared_catalog+runtime_probe", complete=True)
        else:
            operation = args.operation
            if args.request_id:
                try:
                    request_id = str(UUID(args.request_id))
                except ValueError:
                    raise ArgumentError("invalid request ID")
            try:
                params = json.loads(args.params)
            except ValueError:
                raise ArgumentError("invalid JSON parameters")
            output = invoke(operation, params, request_id)
    except ArgumentError:
        output = result(operation, "error", reason="invalid_arguments", request_id=request_id)
    except (OSError, ValueError, TypeError):
        output = result(operation, "error", reason="adapter_error", request_id=request_id)
    sys.stdout.write(json.dumps(output, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    return EXIT_CODES[output["status"]]
