# Changelog

## Unreleased — iOSRemoteBridge computer-use integration

- Add a portable `ios-computer-use` skill using the existing iOSRemoteBridge MCP tools, plus a working-directory-independent stdio launcher. Keep the system-service CLI dependency-free.
- Verify JPEG observation, tap, swipe, Home and visible ASCII entry on the existing iOS 16.1.1 installation. Record the launch error with an observed UI effect; do not retry automatically.
- Keep AX, Unicode input, observation IDs and two-host model image delivery explicitly unverified or unavailable. No device plugin installation or respring is needed for this integration.

## 0.12.0 — Fix review findings and replace the SpringBoard mailbox

- Replace shared command/result files with a peer-authenticated local Unix socket, restrictive permissions, bounded framing, generation IDs, expiry checks and duplicate rejection. Remove the native Bluetooth write action.
- Keep the arm64e shim transport in C and hold asynchronous radio/Bluetooth managers for the process lifetime. Recoverable installation attempts and the final device checks are documented in `docs/review-fixes-0.12.0.md`.
- Confirm created calendars/reminders by new stable ID and account/list, and distinguish failed deletion readback from confirmed absence.
- Detect Live Activity body, lifecycle and presence changes; retain body samples.
- Add sorted calendar event pagination with truthful completeness, and verify event times and notes after creation.
- Preserve filesystem search failures and return relative match locations.
- Validation: 125 Python tests on Windows and device, 19 native fixture checks, 14 dedicated device checks. Real Live Activity change acceptance awaits the test App entering the foreground; its body-change regression passes offline.

## 0.11.0 — Reminders through private ReminderKit

- Add `native/reminders/RemindersBridge.m` using ReminderKit `REMStore` and `REMSaveRequest`.
- Implement `reminders.lists`, `reminders.list`, `reminders.create`, `reminders.update`, `reminders.complete` and `reminders.delete`.
- Explain why EventKit is insufficient: authorization=3 but zero reminder calendars; REMStore exposes the account and list.
- Device acceptance: read the user's reminder, then create/update/complete/delete a test reminder; final list returned to baseline and the user's reminder was untouched.
- 106 Python tests pass; native build now produces six helpers.

## 0.10.0 — Calendar events

- Extend the EventKit calendar helper with `calendar.events`, `calendar.event_create` and `calendar.event_delete`.
- Enforce explicit calendar IDs, ISO-8601 date ranges and readback verification.
- Device acceptance: create a test calendar and event, list it, delete the event (count 0), delete the calendar, final count 9.
- Event IDs are EventKit identifiers (not UUIDs); validate them as bounded strings.
- 97 Python tests pass.

## 0.9.0 — EventKit calendar support

- Add `native/calendar/CalendarBridge.m` using EventKit with CalendarDaemon TCC entitlements.
- Implement `calendar.list`, `calendar.create` and `calendar.delete` with source selection and readback.
- Device acceptance on iPhone SE 2 / iOS 16.1.1 / 20B101: list 9 calendars, create one on iCloud, verify by list, delete, final count 9.
- Document the TCC/EventKit path constraint (`/var/jb/usr/local/bin` required) and the reminder-account blocker.
- 92 Python tests pass; extend native build to five helpers.

## 0.8.0 — System Clock alarms through MobileTimer

- Add native helper `native/alarms/AlarmsBridge.m` using the private MobileTimer `MTAlarmManager`.
- Sign the helper with `com.apple.private.mobiletimerd` and the MobileTimer mach-lookup entitlement; this is required for the alarm service.
- Implement `alarms.list`, `alarms.create`, `alarms.update`, `alarms.set_enabled` and `alarms.delete` with readback verification.
- Device acceptance on iPhone SE 2 / iOS 16.1.1 / 20B101: create 23:57, list, update to 23:56, disable/enable, delete, final list absent; test alarm removed.
- 84 Python tests pass; extend `tools/build_native.py` to build and sign four helpers.

## 0.7.0 — Read-only network and Bluetooth state

- Add read-only `wifi`, `airplane` and `bluetooth` settings through the ElleKit SpringBoard bridge.
- Add bridge action `get_bluetooth`; expose Wi-Fi/airplane/Bluetooth state via `settings.get`.
- Reject writes to read-only settings with `unavailable/read_only_setting` before any bridge command.
- Device acceptance on iPhone SE 2 / iOS 16.1.1 / 20B101: Wi-Fi enabled/associated, airplane off, Bluetooth off; 71 Python tests pass.
- Document that BluetoothManager `setEnabled:` returns no effective change in both CLI and SpringBoard contexts.

## 0.6.0 — ElleKit SpringBoard bridge

- Add optional ElleKit tweak `native/ellekit/SpringBridge.m` for settings that require SpringBoard context.
- Implement `low_power` and `orientation_lock` in `settings.get` / `settings.set` through a fixed command/result file protocol.
- Add read-only bridge actions for Wi-Fi/airplane state; they are not exposed as writable settings.
- Add `tools/build_ellekit_bridge.py` to build, sign, install and optionally respring; keep the bridge outside the Debian package.
- Device acceptance on iPhone SE 2 / iOS 16.1.1 / 20B101: low_power and orientation_lock get/set/readback/restore; 69 Python tests pass.
- Document the bridge architecture and security boundary; update README, service scope, architecture, verification, skill and handoff.

## 0.5.0 — Files, browser, weather and activity watching

- Add bounded `files.list` / `files.search` / `files.read` adapters with explicit paths and truncation flags.
- Add `browser.search` (DuckDuckGo HTML with Bing fallback), `browser.read` and `browser.open` through a new `icb-open-url` helper.
- Add `weather.current` / `weather.forecast` through Open-Meteo with provider attribution and explicit units/timezone.
- Add bounded `activities.watch` polling with explicit duration, interval, timeout and optional stop-on-change.
- Build all three native helpers in one `tools/build_native.py` run; update capability readiness and version to 0.5.0.
- Device acceptance on iPhone SE 2 / iOS 16.1.1 / 20B101 for all new operations; 62 Python tests pass.
- Document remaining blockers for system alarms, reminders and risky settings; add `docs/COMPLETION_REPORT.md` and `evidence/features-0.5.0.json`.

## 0.4.0 — Settings brightness adapter

- Extend `native/settings` with the `brightness` setting through `BrightnessSystemClient` (`DisplayBrightness`).
- Extend `settings.get` / `settings.set` to validate per-setting source and readback tolerance; `brightness` uses a 0.005 tolerance.
- Device acceptance on iPhone SE 2 / iOS 16.1.1 / 20B101: read 0.8431398868560791, set 0.783139887, read back 0.7831399440765381, restore the original value; 34 Python tests pass.
- The helper also completed the get/set/readback/restore sequence as the mobile user; volume remained unchanged.

## 0.3.0 — Settings volume adapter

- Add `native/settings` Objective-C helper for the media volume through `AVSystemController`.
- Implement `settings.get` and `settings.set` for `volume` with strict parameter validation, readback verification and explicit unavailable/error reasons.
- Extend `tools/build_native.py` to build both `icb-activities` and `icb-settings` in one signed build.
- Device acceptance on iPhone SE 2 / iOS 16.1.1 / 20B101: read, change to 0.31, read back, restore to 0.0; 31 Python tests pass.
- Other settings, alarms, reminders, browser, weather, files and monitoring remain planned unless separately implemented.

## 0.2.0 — Independent project

- Establish iOS Control Bridge as a standalone repository and client-neutral system-service project.
- Add a Python 3.9+ JSON CLI, explicit capability registry and request/result contracts.
- Port the native Live Activity reader to independent names and a repository-local build.
- Add device identity querying and the portable `ios-control-bridge` skill.
- Define the scope and acceptance criteria for settings, system alarms, reminders, browser queries, weather and monitoring; these adapters remain unimplemented until separately verified.
