# iOS Control Bridge

This repository is an independent, client-neutral bridge for querying and controlling everyday iOS system services. Keep runtime, build and tests independent of any coding agent, AI account or old workspace.

- Preserve the native Live Activity reader's verified iOS 16.1.1 / 20B101 boundary until another build is tested. Check real Objective-C method encodings before calling private selectors. Invalidate observation tokens before releasing them.
- Distinguish implemented, device-verified and planned operations. Unimplemented adapters return unavailable; never synthesize system state or claim a write succeeded from an IPC acknowledgement alone.
- Use argument arrays for subprocesses. Keep timeouts, bounded results, explicit target IDs and observation timestamps. Read device state back after implemented writes.
- Follow the user's existing authorization. Resolve routine, reversible implementation choices directly. Do not test network-disconnecting switches, audible alarms or destructive operations merely to validate a repository migration.
- Keep credentials, device addresses, SSH host keys, raw personal records and crash dumps outside Git. Use sanitized summaries for device evidence.
- Run `python -m unittest discover -s tests -v` for the Python core. Build native code with `python tools/build_native.py`; native results require a real compatible device.
- The portable skill is `skills/ios-control-bridge`. Its instructions must reflect actual capabilities and preserve normal automatic discovery.
