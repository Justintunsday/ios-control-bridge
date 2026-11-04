# Changelog

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
