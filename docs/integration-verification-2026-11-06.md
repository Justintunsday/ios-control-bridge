# Three-project integration verification — 2026-11-06

The source integration now follows this path:

```text
opencode-ios-bridge setup/doctor
  → iosctl opencode setup/doctor
  → configured iosctl iosremote --stdlib
  → iOSRemoteBridge automation.mcp_stdio
```

The SDK and stdlib adapters publish the same 14-tool catalog and use the same
argument validation, connection policy and image validation. System-service
operations continue through the fixed iosctl registry. Generated instructions
provide the actual CLI and skill paths and distinguish local services from a
paired remote UI session.

| Validation | Result |
| --- | --- |
| Windows, iOSRemoteBridge, MCP SDK 2.3.0 | 33 passed, including actual SDK/stdlib catalog and routing parity. |
| Windows, iOS Control Bridge | 170 passed, including real cross-repository subprocess discovery. |
| Windows, OpenCode iOS | 69 passed, including the shell launcher and a Python payload without tools/. |
| iPhone, iOS 16.1.1 / 20B101, Python 3.9.9 | 28 passed, 1 optional SDK test skipped across the three integration suites. |
| YAML, shell syntax and portable skill validation | Passed. |

The on-device tests ran as mobile (UID 501) from isolated temporary sources.
They verified configuration preview and apply, preservation of existing
configuration/comments, backup and repeatability, process startup, lazy MCP
discovery and service capability reporting. Their intentionally invalid pairing
fixture proves discovery does not read pairing contents or open a device
session. No input action or active OpenCode configuration was changed. Temporary
device test files were removed afterwards.

A separate viewing-only check used the existing private pairing file and the
new stdlib entry. MCP discovery returned 14 tools. The actual device-info call
failed with a refused TCP connection (Windows socket error 10061), so **a live
screen image was not obtained or verified**. The adapter was disconnected; no
input was attempted. This report does not claim physical validation of the new
double-tap, long-press or app-launch tools, or a new OpenCode-to-model image round
trip.

No new native package was built or installed during this change. The source
packaging paths include the optional launchers/backend, and CI checks extracted
backend discovery. Native package assembly still requires the normal Theos/Xcode
workflow. Existing native code and verified OS-build boundaries were not changed.

The [sanitized machine-readable evidence](../evidence/three-project-integration-2026-11-06.json)
records base revisions, changed-source hashes, test counts and the on-device
archive hash. Pairing contents, device addresses, SSH identity and raw personal
records are excluded. See [setup and diagnostics](opencode-integration.md) for
the supported commands and their validation scope.
