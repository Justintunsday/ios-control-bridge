"""Launch an existing iOSRemoteBridge MCP checkout from any working directory.

The optional MCP dependency belongs to that backend's environment. This launcher
does not add dependencies to iosctl, read pairing secrets, or install a device service.
"""
import argparse
from pathlib import Path
import runpy
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-root", required=True, type=Path,
                        help="absolute path to the reviewed iOSRemoteBridge checkout")
    parser.add_argument("--config", required=True, type=Path,
                        help="absolute path to the private existing client pairing JSON")
    parser.add_argument("--control", action="store_true",
                        help="enable input in the paired, unlocked session")
    parser.add_argument("--stdlib", action="store_true",
                        help="use the Python 3.9-compatible MCP transport without the optional SDK")
    args = parser.parse_args(argv)
    if not args.bridge_root.is_absolute() or not args.config.is_absolute():
        parser.error("--bridge-root and --config must be absolute paths")
    bridge_root = args.bridge_root.resolve()
    required = ["automation/__init__.py", "automation/client.py", "automation/protocol.py"]
    if not args.stdlib:
        required.append("automation/mcp_server.py")
    if not all((bridge_root / name).is_file() for name in required):
        parser.error("--bridge-root is not an iOSRemoteBridge automation checkout")
    sys.path.insert(0, str(bridge_root))
    sys.argv = ["automation.mcp_server", "--config", str(args.config.resolve())]
    if args.control:
        sys.argv.append("--control")
    if args.stdlib:
        if (bridge_root / "automation/mcp_stdio.py").is_file():
            # The backend owns the tool catalog for both transports. Keep the
            # original shim only for already-reviewed, older backend checkouts.
            runpy.run_module("automation.mcp_stdio", run_name="__main__")
        else:
            legacy = Path(__file__).resolve().parents[2] / "tools/iosremote_stdio.py"
            if not legacy.is_file():
                parser.error("update iOSRemoteBridge for native stdlib MCP; legacy shim is not installed")
            print("iosremote: older backend; using the legacy ten-tool adapter. "
                  "Update iOSRemoteBridge for the full stdlib catalog.", file=sys.stderr)
            runpy.run_path(str(legacy), run_name="__main__")
    else:
        runpy.run_module("automation.mcp_server", run_name="__main__")


if __name__ == "__main__":
    main()
