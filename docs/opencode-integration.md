# OpenCode, system services and visual automation

The three projects share one optional integration path:

| Project | Responsibility |
| --- | --- |
| [OpenCode iOS](https://github.com/Justintunsday/opencode-ios) | Agent, provider configuration and terminal client; optional `opencode-ios-bridge` launcher. |
| iOS Control Bridge | Fixed `iosctl` system-service operations, client setup and diagnostics. |
| [iOSRemoteBridge](https://github.com/Justintunsday/iOSRemoteBridge) | Paired TLS transport, screen images and input; one catalog for SDK and stdlib MCP adapters. |

System services execute where `iosctl` runs. A desktop can view a paired phone,
but its local `iosctl` cannot query that phone's iOS services. Use the existing
device terminal for those operations. Pairing does not provide an SSH channel.

## Configure

Use Python 3.9+ and updated copies of both bridges. iOSRemoteBridge must include
`automation/mcp_stdio.py` and `mcp_tools.py`. New upstream rootless builds include
these under `/var/jb/usr/lib/iosremotebridge`; a source checkout works too.
Reuse an existing private pairing JSON. Its contents are never copied into
OpenCode configuration or the generated instructions.

Find the configuration actually used by the OpenCode server with `opencode debug
paths` and `opencode debug config`. Root and mobile servers can use different
homes and configuration files. Configure the identity running the server.

From any working directory, preview the integration:

```sh
python3 -B /path/to/ios-control-bridge/bin/iosctl opencode setup \
  --bridge-root /path/to/iOSRemoteBridge \
  --config /private/path/client-config.json \
  --opencode-config /actual/config/opencode.jsonc \
  --control
```

Append `--apply` to write the preview. Omit `--control` for a viewing session.
Paths must be absolute; quote paths with spaces. `--python` can select another
absolute Python executable. No pip packages, provider key or online device are
needed for configuration or tool discovery.

Setup adds the `iosremote` MCP server and an `ios-bridges.md` instruction path.
It uses `mcp.servers` for new v2 configurations and retains an existing legacy
`mcp` layout. Other servers, provider credentials, instructions and unrelated
JSONC text/comments are retained. Existing managed server options, including an
explicitly disabled server, remain in place. An unrelated server with the same
name is preserved; choose `--server-name` instead. Both files are backed up
before replacement, and rerunning unchanged setup creates no extra backups.

The generated guide supplies actual service CLI and skill paths, the choice
between fixed services and visual tools, readback requirements and UI session
lifecycle. Portable skills stay in this repository; no duplicate skill install
is required. The Python integrations live in `src/` and work in the rootless
package without a `tools/` directory.

After applying, reload the actual OpenCode server (`opencode reload` for a normal
server, or restart the optional root service) and reopen its client. Then run
`opencode mcp list`. A connected catalog does not prove phone connectivity.

## Diagnose

```sh
python3 -B /path/to/ios-control-bridge/bin/iosctl opencode doctor \
  --bridge-root /path/to/iOSRemoteBridge \
  --config /private/path/client-config.json \
  --opencode-config /actual/config/opencode.jsonc
```

Doctor verifies the configured command and instructions, launches the actual
stdio process, performs MCP initialization, checks all 14 tool names and reads
local connection status. It also reports local service capability readiness.
It does not connect to the phone, read pairing contents, take screenshots or
change device settings. `ready` describes that integration check;
`device_connection_tested` remains false. A desktop's `not_ios` service report
is distinct from a working remote UI adapter.

Observe an actual `get_device_info` and `get_screen_frame` through the model
before claiming device or image delivery. Input requires its own observation
and outcome verification. The optional `launch_app`, long-press and double-tap
tools retain the backend's experimental device-validation boundary.

## OpenCode iOS launcher

New OpenCode iOS packages include `opencode-ios-bridge`. The same setup and doctor
arguments can follow that command. It defaults to the Control Bridge package at
`/var/jb/usr/lib/ios-control-bridge` and Python at `/var/jb/usr/bin/python3`.
For a checkout, start with `opencode-ios-bridge --icb-root /absolute/checkout` or
set `IOS_CONTROL_BRIDGE_ROOT`. `IOS_BRIDGE_PYTHON` overrides the Python executable.
The launcher does not install packages or enable the optional root/Siri services.

## Existing launch commands and tests

`tools/run_iosremote_mcp.py` remains compatible with earlier callers. The packaged
entry is `iosctl iosremote --bridge-root ... --config ... --stdlib [--control]`.
Both delegate to the backend's native stdlib server. With an older reviewed
checkout, the source launcher can use the original ten-tool shim and prints a
warning to stderr. New setup requires the full native backend.

Run the cross-repository host test explicitly:

```sh
IOSREMOTE_BRIDGE_TEST_ROOT=/absolute/iOSRemoteBridge \
  python3 -m unittest discover -s tests -v
```

In the OpenCode iOS checkout, set both `IOS_CONTROL_BRIDGE_TEST_ROOT` and
`IOSREMOTE_BRIDGE_TEST_ROOT` and run its tests. That test copies only packaged
Python files into a temporary tree, runs the shell launcher and checks setup,
MCP discovery and service capabilities from an unrelated working directory.
It uses an intentionally invalid pairing fixture to prove discovery is lazy.
The manually dispatched `test-integration.yml` workflow accepts explicit refs
for both companion repositories. Host tests do not replace native packaging
or physical-device acceptance.

The [November 6 verification record](integration-verification-2026-11-06.md)
separates passed Python integration tests from the unavailable live UI check.
