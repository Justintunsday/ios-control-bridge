# iOS Control Bridge

Query and control everyday iOS services from a terminal or an AI client.

[![Version](https://img.shields.io/badge/version-0.13.0-blue)](pyproject.toml)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB)](pyproject.toml)
[![Device tested](https://img.shields.io/badge/device_tested-iOS_16.1.1-555555)](docs/verification.md)

A standalone Python CLI and native Objective-C/Swift helpers expose system
settings, alarms, calendars, reminders, Live Activities, files and network
queries through a consistent JSON interface. The Python core has no third-party
runtime dependencies and works independently of any coding agent, model account
or AI SDK.

**Experimental, with device verification on iPhone SE 2 (iPhone12,8), iOS 16.1.1
/ 20B101 and Dopamine rootless.** Private API support is verified per operation
and OS build. See the [device reports](docs/verification.md) and
[0.12.0 review and fixes](docs/review-fixes-0.12.0.md) for evidence and limits.

## Implemented

| Area | Operations or family | Details |
| --- | --- | --- |
| Device information | `device.info` | Model, OS build, execution identity and bootstrap evidence. |
| Siri language | `siri.language.get`, `siri.language.set` | Effective recognition language and independently verified Mandarin/English primary-language selection. Requires the optional native helper. |
| Live Activities | `activities.get`, `activities.watch` | Read a selected activity's cross-app content and state; monitor changes with bounded polling. |
| Settings | `settings.get`, `settings.set` | Read and change media volume, brightness, low power mode and orientation lock, with readback. Wi-Fi, airplane mode and Bluetooth are read-only. |
| Alarms | `alarms.*` | List, create, update time/label, enable/disable and delete system Clock alarms through private MobileTimer APIs. |
| Calendars | `calendar.*` | List/create/delete calendars and query/create/delete events through EventKit, with explicit IDs, date ranges and pagination. |
| Reminders | `reminders.*` | List reminder lists; query, create, rename, complete and delete reminders through private ReminderKit APIs. |
| Files | `files.list`, `files.search`, `files.read` | Bounded results and file reads under an explicitly supplied absolute path. |
| Apps | `apps.list`, `apps.get`, `apps.store_info`, `apps.install`, `apps.download`, `apps.uninstall` | App Store free offers, local/HTTPS IPA installation and exact bundle-ID removal, with independent readback. See [app management](docs/apps.md). |
| Web queries | `browser.search`, `browser.read`, `browser.open` | Web search, page text extraction and requests to open HTTP(S) URLs through LaunchServices. |
| Weather | `weather.current`, `weather.forecast` | Open-Meteo data for supplied coordinates, including provider attribution, units and timestamps. |
| Visual automation | Optional iOSRemoteBridge MCP tools | Screenshots, taps, swipes, text input and Home. See [computer use](#ai-clients-and-computer-use) for setup and verification boundaries. |

Service operations run through `iosctl`. Visual automation uses the separate
[iOSRemoteBridge](https://github.com/Justintunsday/iOSRemoteBridge) device plugin
and its paired TLS client. Both projects can be used together: this repository
provides system-service adapters, portable skills and the MCP launcher;
iOSRemoteBridge provides screen streaming and UI input.

Runtime availability is reported by `iosctl capabilities`. An implemented
adapter can still be unavailable when its helper, entitlement or supported OS
build is missing.

## Get started

### Requirements

- Python 3.9 or later.
- A jailbroken iPhone with the permissions required by the selected service.
  The verified environment is iOS 16.1.1 / 20B101 with Dopamine rootless.
- Existing `clang`, `swiftc`, `ldid` and an iPhoneOS SDK to build native helpers.
  Apple SDKs are supplied separately.
- ElleKit for settings that use the optional SpringBoard bridge.

Run device commands in the iPhone's terminal or through an existing SSH
connection. A Windows or other desktop checkout can inspect the catalog and run
portable tests; iOS service queries on a non-iOS host report `unavailable` with
reason `not_ios`.

On Windows, use `py -3` where the examples use `python3`.

### Clone and inspect capabilities

```sh
git clone https://github.com/Justintunsday/ios-control-bridge.git
cd ios-control-bridge

python3 -B bin/iosctl --version
python3 -B bin/iosctl capabilities
python3 -B bin/iosctl capabilities --service settings
```

The CLI runs directly from the checkout. For an installed `iosctl` command,
use `python3 -m pip install --no-deps -e .` in a suitable Python environment.

### Build native helpers

On the device, point the builder at an existing iPhoneOS SDK:

```sh
python3 tools/build_native.py --sdk /path/to/iPhoneOS.sdk
```

Replace the SDK path with your installed SDK. The builder compiles and signs
eight helpers under `build/native/`, then writes a manifest with source and binary
hashes:

| Helper | Service |
| --- | --- |
| `icb-activities` | Live Activity content and state |
| `icb-settings` | Media volume and screen brightness |
| `icb-alarms` | System Clock alarms |
| `icb-calendar` | Calendars and events |
| `icb-reminders` | Reminder lists and items |
| `icb-open-url` | LaunchServices URL opening |
| `icb-siri-language` | Effective Siri recognition language |
| `icb-apps` | App inventory, App Store and IPA installation, exact-ID removal |

Calendar and reminder helpers must also be installed at
`/var/jb/usr/local/bin/icb-calendar` and `/var/jb/usr/local/bin/icb-reminders`.
These paths matter to the verified TCC/private-framework access behavior. See
[deployment records](docs/verification.md) and the
[native API reference](skills/ios-control-bridge/references/private-apis.md).

After building, install those two signed helpers on the device:

```sh
sudo install -d -m 755 /var/jb/usr/local/bin
sudo install -m 755 build/native/icb-calendar /var/jb/usr/local/bin/icb-calendar
sudo install -m 755 build/native/icb-reminders /var/jb/usr/local/bin/icb-reminders
```

Low power mode, orientation lock and read-only network/Bluetooth state require
the additional [ElleKit SpringBoard bridge](docs/ELLEKIT_BRIDGE.md). Its installer
backs up existing files; `--build-only` builds without installing, and an
explicit `--respring` reloads SpringBoard. Upgrade the CLI, native helpers and
shim together: version 0.12.0 uses the Unix socket protocol instead of the older
file mailbox.

### Query services

```sh
python3 -B bin/iosctl call device.info
python3 -B bin/iosctl call settings.get --params '{"setting":"brightness"}'
python3 -B bin/iosctl call alarms.list
python3 -B bin/iosctl call calendar.list
python3 -B bin/iosctl call reminders.lists
python3 -B bin/iosctl call files.list --params '{"path":"/var/mobile","limit":10}'
python3 -B bin/iosctl call browser.search --params '{"query":"iPhone terminal","limit":3}'
python3 -B bin/iosctl call weather.current --params '{"latitude":52.52,"longitude":13.41}'
```

Read a Live Activity using its actual UUID:

```sh
python3 -B bin/iosctl call activities.get \
  --params '{"activity_id":"ACTIVITY_UUID","timeout_ms":5000}'
```

Make a targeted change and inspect the resulting state:

```sh
python3 -B bin/iosctl call settings.set --params '{"setting":"brightness","value":0.5}'
python3 -B bin/iosctl call settings.get --params '{"setting":"brightness"}'
```

Use the returned stable IDs for alarm, calendar and reminder mutations. Parameters
and service-specific behavior are described in the
[service reference](skills/ios-control-bridge/references/services.md).

## Result contract

Both `capabilities` and `call` return `ios-control-bridge.result.v1` JSON with an operation,
request ID, status, observation time and `complete_for_scope`. Results can also
include data, a reason and the actual data source. A complete empty query is
distinct from a failed or incomplete query.

| Status | Exit code | Meaning |
| --- | --- | --- |
| `verified` | `0` | The adapter verified the result for the requested scope. |
| `partial` | `2` | Some requested data or verification is incomplete. |
| `unavailable` | `3` | The environment, permission, helper or operation is unavailable. |
| `error` | `4` | Invalid input or an adapter error. |

Capability entries distinguish `implemented`, recorded `validation` and current
`runtime.ready_to_query`. Capability discovery does not perform every service
query. Mutations use readback where supported; an IPC or launch acknowledgement
alone does not prove the requested system or UI effect.

Event queries support `limit` and `offset`; truncated results report their
coverage and the next offset. Clients should retain these limits and refresh the
query if the source changes while paging.

## AI clients and computer use

For OpenCode iOS, use the optional `iosctl opencode setup` and `doctor` commands
to merge MCP configuration, supply exact service paths and verify the shared
14-tool backend. See the [three-project integration guide](docs/opencode-integration.md).
New OpenCode iOS packages expose the same workflow as `opencode-ios-bridge`.

The service CLI can be called by any client that executes commands and parses
JSON. Two portable skills provide task instructions:

| Skill | Purpose |
| --- | --- |
| [ios-control-bridge](skills/ios-control-bridge/SKILL.md) | Query and change supported system services through fixed `iosctl` operations. |
| [ios-computer-use](skills/ios-computer-use/SKILL.md) | Observe and operate the visible iPhone UI through iOSRemoteBridge. |

Use an exact service adapter when one is available. For UI tasks, install and
pair the iOSRemoteBridge plugin separately, keep its backend checkout available,
and reference the private pairing JSON by absolute path. The
[backend guide](skills/ios-computer-use/references/backend.md) includes Codex and
OpenCode configuration examples.

The Python 3.9-compatible MCP entry point uses the standard library:

```sh
python3 /path/to/ios-control-bridge/tools/run_iosremote_mcp.py \
  --bridge-root /path/to/iOSRemoteBridge \
  --config /private/path/client-config.json \
  --control --stdlib
```

Replace all paths with real absolute paths. Omit `--control` for viewing only.
With an updated backend this entry point delegates to its native 14-tool stdlib
server and reuses the pinned TLS client. The original ten-tool shim remains a
source-only fallback for older checkouts and emits an upgrade warning.
The alternative SDK entry point, selected by omitting `--stdlib`, requires the
backend's optional MCP dependencies and Python 3.10 or later.

Ordinary text should use `insert_text`, which submits literal Unicode without
IME candidate selection. It supports up to 1024 UTF-16 code units; the older
`type_text` retains US-layout ASCII key semantics. Direct insertion requires a
compatible native plugin with the [Unicode input patch](https://github.com/Justintunsday/iOSRemoteBridge/pull/2).
Check `input_diagnostics.literal_text_ready` and observe the focused field before
input. Insertion does not press Return or send a message.

Chinese, emoji, combining characters, newlines and boundary-length text passed
readback in an owned UIKit fixture. The updated plugin was installed and reported
ready; a full deployed MCP text-input round trip, secure fields and arbitrary
custom editors remain unverified. See the [direct-input report](docs/iosremote-direct-text.md).

UI actions follow screenshot, action, fresh observation. One paired device
session is available at a time; locking the phone ends it. Disconnect when done,
and inspect the UI after an ambiguous outcome before issuing another action.
Keep pairing secrets and raw personal records local.

## Optional native Siri adapter

The [native Siri integration](docs/native-siri.md) keeps the original Siri
interface and speech presentation while an on-device OpenCode service answers
recognized speech and typed questions. On iOS 16.1.1 / 20B101, real voice requests
reached OpenCode and the phone owner confirmed the answers were displayed and
spoken by the original Siri interface. It adds no visual effects or screen-control
session. This optional integration lives outside the client-neutral core and
requires its own build, installation and enable step.

Speech recognition still uses Siri. The [language diagnostic and controls](docs/siri-language.md)
explain primary-language selection and the separate validation needed for mixed
Mandarin/English speech.

## Development and verification

```text
bin/iosctl                CLI entry point
src/ios_control_bridge/   Python registry, adapters and result contract
native/                   Objective-C and Swift helpers; optional SpringBoard shim
integrations/             Optional client-specific adapters, including native Siri
skills/                   Portable service and computer-use instructions
tools/                    Native builds, verification and MCP launchers
tests/                    Portable Python regression tests
schemas/                  Request and result schemas
docs/ and evidence/       Design notes and sanitized verification records
```

Run portable tests on the development host:

```sh
python3 -m unittest discover -s tests -v
```

On the verified device, `python3 tools/test_native.py` builds and runs isolated
native fixtures. These use in-memory framework substitutes and do not replace
loading the real SpringBoard shim or observing actual service writes.

The latest [direct-input evidence](evidence/iosremote-direct-text-2026-11-05.json)
records 138 passing Python tests and the Unicode fixture results. The
[native Siri evidence](evidence/native-siri-2026-11-05.json) records the subsequent
151-test run and the owner-confirmed native voice/display checks. The
[0.12.0 review](docs/review-fixes-0.12.0.md) records the separate native fixture and
system-service checks, including recovery from deployment failures. Validation
applies to the recorded build, target and observation window.

## Documentation

Supporting documents currently include English and Chinese material.

| Document | Contents |
| --- | --- |
| [Architecture](docs/architecture.md) | Service routing, request/result contracts and native adapters. |
| [Device verification](docs/verification.md) | Dated service read/write results and compatibility observations. |
| [Review fixes](docs/review-fixes-0.12.0.md) | Version 0.12.0 fixes, regression results and deployment recovery. |
| [Live Activities](docs/live-activities.md) | Native reader, payload handling and OS-build boundary. |
| [SpringBoard bridge](docs/ELLEKIT_BRIDGE.md) | Optional settings shim, local IPC, installation and lifecycle constraints. |
| [Computer-use integration](docs/iosremote-computer-use.md) | iOSRemoteBridge integration and observed mobile OpenCode UI tasks. |
| [Direct Unicode input](docs/iosremote-direct-text.md) | Literal insertion, native fixture evidence and remaining checks. |
| [Native Siri](docs/native-siri.md) | Stock Siri UI/TTS with optional OpenCode answers, installation and device evidence. |
| [Siri language](docs/siri-language.md) | Effective-language queries, verified preference writes and mixed-speech limits. |
| [Private API reference](skills/ios-control-bridge/references/private-apis.md) | Framework routes, helper paths and entitlements. |
| [Roadmap](docs/roadmap.md) | Broader service and automation goals. |
| [Developer handoff](HANDOFF.md) | Repository layout and implementation guidance. |

Cellular and Focus controls, semantic weekday alarm recurrence and a persistent
monitoring/notification runner remain future work. The
UI backend also lacks an accessibility element tree and device-side rejection
of stale screenshot coordinates. New services and OS builds need their own
implementation and verification records.
