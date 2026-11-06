# Installed three-project device acceptance — 2026-11-06

Three new rootless packages were built and installed on the authorized iPhone
SE 2 / iOS 16.1.1 (20B101). Python is 3.9.9; the existing Node runtime remains
26.13.0-2. Device credentials and addresses are excluded from this report.

| Package | Installed version | Build source |
| --- | --- | --- |
| iOSRemoteBridge | `0.1.0~dev+repo.20261106.2` | `c9f04078f94ce99413233341f19d70f69c784bf7`; [native build](https://github.com/Justintunsday/iOSRemoteBridge/actions/runs/42201358758). |
| Control API | `0.12.0+repo.3` | `6b517499d3f36e2f79697ea3a83e2289ae303f64`; native helpers, settings shim and Siri transport rebuilt using the existing device toolchain/SDK. |
| OpenCode iOS | `2.2.5-5+integration.1` | `34244513972805a9375ed95246f7e31a262775a8`; [package build](https://github.com/Justintunsday/opencode-ios/actions/runs/42201572461), retaining the reviewed CLI, renderer and exact Node dependency. |

The source iOSRemoteBridge build initially placed the Python backend under
`/var/jb/var/jb`. Theos prefixes its staged tree during rootless packaging.
Commit `c9f0407` stages the Python files without that prefix and rejects a
duplicated prefix in the extracted-package test. The corrected build passed;
the failed artifact was not installed.

The CI packages were given the explicit test revisions above without modifying
their payload bytes. The Control Bridge package also includes its verified
fixed calendar, reminder and Siri-language helper paths. Package checksums and
source revisions are in the [sanitized evidence](../evidence/device-integration-2026-11-06.json).
These are device-test packages, not a new public stable release.

## Observed results

| Check | Result |
| --- | --- |
| Install and payload audit | All three packages installed. 125 regular files and 3 links matched the package bytes, modes and targets. |
| Native fixtures | 19 checks passed against compiled native control flow; no personal records or real alarms were modified. |
| Python source regression on device | 170 tests ran; 1 optional cross-repository test skipped. |
| mobile and root configuration | Both setup/doctor paths passed, discovered 14 stdlib tools and reported 32 ready service operations. |
| Production fixed service | UID 501 read device identity and brightness. A bounded brightness change was read back, then the original value was restored and read back. |
| Real image delivery | Current 750×1334 JPEG images were obtained over pinned TLS and inspected. |
| UI input | Tap, swipe, Home, literal Chinese/emoji insertion, double-tap text selection and an 800 ms icon long-press were visibly observed. |
| OpenCode → provider → MCP | A new owned DeepSeek Flash session completed device-info, screen-frame, shell/iosctl and disconnect tool calls. The model identified the actual Home Screen with widgets and reported its dimensions and brightness. |
| Session cleanup | The model's disconnect returned `connected:false`; the owned verification session was removed. Direct test adapters also disconnected. Search fixtures and UI menus were cleared. |
| Reload health | SpringBoard was reloaded once to load the rebuilt libraries; it remained running, with no new SpringBoard crash report or safe mode observed. |

Existing pairing, certificate, server password and provider-auth file hashes
were preserved. Root OpenCode configuration retained its non-MCP fields. The
new mobile configuration uses a private copy of the existing pairing, not a new
pairing identity. Earlier packages and relevant configuration were backed up
locally on the device before installation.

The UI tests briefly overlapped local screen use; actions were paused and
re-observed after the owner confirmed the screen was available. A selection menu
also covered one intended caret tap and triggered Paste. The search was cleared;
that intermediate capture was discarded. No message, private record or clipboard
contents are included in this report.

## Limits observed during this run

- Experimental `launch_app` returned a backend refusal for a confirmed installed
  app. It was not replayed or counted as a pass. Use observed app icons when this
  private API refuses a request.
- `opencode mcp list --server ...` reported the connected server in the verified
  project directory, while the root-home location reported an empty list. The
  actual agent session and its four completed tool receipts establish the
  tested project context; this report does not claim identical behavior for
  every location or profile.
- The legacy `type_text` path, secure/custom text fields, rotation, multi-touch,
  long unattended operation and other OS builds were not newly accepted here.
- The reported frame telemetry is not a glass-to-glass latency or sustained
  60 FPS measurement. The test did not disable auto-lock or bypass a passcode.

Raw screenshots, provider responses, pairing/configuration backups and device
build logs remain private local artifacts. The public evidence contains only
package/source hashes, check results and sanitized receipts.
