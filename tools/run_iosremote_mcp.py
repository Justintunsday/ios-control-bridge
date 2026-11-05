"""Launch an existing iOSRemoteBridge MCP checkout from any working directory.

The optional MCP dependency belongs to that backend's environment. This launcher
does not add dependencies to iosctl, read pairing secrets, or install a device service.
"""
import argparse
from pathlib import Path
import runpy
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-root", required=True, type=Path,
                        help="absolute path to the reviewed iOSRemoteBridge checkout")
    parser.add_argument("--config", required=True, type=Path,
                        help="absolute path to the private existing client pairing JSON")
    parser.add_argument("--control", action="store_true",
                        help="enable input in the paired, unlocked session")
    args = parser.parse_args()
    if not args.bridge_root.is_absolute() or not args.config.is_absolute():
        parser.error("--bridge-root and --config must be absolute paths")
    bridge_root = args.bridge_root.resolve()
    if not all((bridge_root / name).is_file() for name in (
        "automation/__init__.py", "automation/client.py", "automation/mcp_server.py"
    )):
        parser.error("--bridge-root is not an iOSRemoteBridge automation checkout")
    sys.path.insert(0, str(bridge_root))
    sys.argv = ["automation.mcp_server", "--config", str(args.config.resolve())]
    if args.control:
        sys.argv.append("--control")
    runpy.run_module("automation.mcp_server", run_name="__main__")


if __name__ == "__main__":
    main()
