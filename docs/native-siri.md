# Native Siri → OpenCode

The optional adapter keeps the existing Siri invocation, interface and speech
presentation. Final recognized speech and typed Siri questions go to a dedicated
OpenCode conversation. Answers return through Siri's own utterance views and
TTS text. There is no added lighting effect, overlay, keyboard automation or VNC
connection.

Speech recognition remains Apple's Siri recognizer. See the
[language diagnostic](siri-language.md) for Mandarin/English input and the fixed
language-settings adapter; replacing the answer backend does not itself add a
multilingual recognizer.

Verified on an iPhone SE (2nd generation), iOS **16.1.1 / 20B101**, with OpenCode
2.2.5. Other builds are rejected by the native hook and backend. This is an
experimental private-API integration; see the dated [evidence](../evidence/native-siri-2026-11-05.json).

## Verified behavior

- A real microphone recognition callback delivered `SASSpeechRecognized` with
  the measured two-object completion block signature. A synthetic SAObjects
  fixture separately checked extraction of the recognized text.
- A complete framework request reached OpenCode and returned the real answer
  as `SAUIAddViews` / `SAUIAssistantUtteranceView`, including `speakableText`.
- Two subsequent real voice requests were intercepted, answered by the backend
  and delivered natively. The phone owner confirmed seeing and hearing the
  OpenCode answer in the original Siri interface.
- The native dylib and root backend remained running during the observation
  window. SpringBoard was not restarted by the installation.
- A later typed request while the device reported locked returned the native
  unlock instruction and created no OpenCode prompt. Disable/re-enable and
  fresh-inode replacement checks passed on the phone. All 151 portable tests
  passed on Windows.

Voice-initiated system writes, unattended wake-word detection, locked-screen
voice requests and other iOS versions have not been separately verified. Existing
service capabilities retain their own validation boundaries. The unit suite
checks that locked requests do not reach OpenCode.

## Components and lifecycle

| Component | Role |
| --- | --- |
| `native/siri/NativeTransport.m` | Build-gated assistantd hooks, turn ownership, stock reply delivery and local IPC. |
| `native/siri/SiriRuntime.h` | Measured Objective-C method and block ABI checks; recognition text extraction. |
| `integrations/siri/server.py` | Root Unix socket service, mobile/root peer checks and device lock gate. |
| `integrations/siri/backend.py` | Optional OpenCode HTTP adapter and dedicated conversation. |
| `integrations/siri/install.py` | Fresh installation, explicit enable and disable. |
| `native/siri/TypedFixture.m` | A synthetic framework client; never opens the microphone or Siri UI. |
| `native/siri/TextExtractionFixture.m` | Synthetic recognition-object fixture. |

The native hook loads only in **assistantd**. It checks every hook ABI before
installing any hook. It intercepts typed questions before native fulfillment;
for speech it consumes the verified final-recognition callback, completes that
callback with its measured ABI and cancels the stock request on the Siri queue.
Stock reply/completion callbacks stay suppressed for the owned turn. New requests,
client cancellation, dismissal and disconnection invalidate stale answers.

The backend uses a mobile-owned `0700` directory under
`/var/mobile/Library/Assistant/ICBSiriBridge`, which assistantd can access. Frames
have a four-byte network-order length and a 64 KiB limit. The client verifies the
server's root peer identity; the server accepts only root/mobile peers. Native
code never receives the OpenCode password. The root service reads it from an
existing private file and only contacts a configured loopback HTTP origin, with
redirects and proxies disabled.

The backend maintains one dedicated `Siri · OpenCode` conversation. A request UUID,
query hash and explicit OpenCode message ID prevent accidental resubmission after
an uncertain POST or process restart. Only a fresh, completed assistant text reply
is spoken; reasoning, tool output and previous answers are excluded. The overall
backend deadline is 36 seconds. Longer tasks return a progress message and remain
available in the chat app. Dismissing Siri hides the reply; an already accepted
OpenCode task can continue. Use the chat app's stop action to interrupt that task.

Transcripts and answers are part of the dedicated OpenCode chat and use its
configured provider. Bridge state contains request metadata and hashes; the
native diagnostic log contains event names and timestamps, without transcripts.

## Build and fresh installation

Use the macOS `build-siri` workflow and download its
`siri-native-development` artifact. The workflow compiles arm64 + arm64e with
ARC and warnings treated as errors. Do not build an injected Foundation dylib
with an unverified on-device compiler.

Copy the repository's `integrations/siri` folder and `NativeBridge.dylib` onto
the verified phone. The phone needs Python 3.9+, ldid, ElleKit and an already
configured local OpenCode service. Run with the jailbreak's normal executable
PATH, as root:

```sh
python3 -B /absolute/path/integrations/siri/install.py install \
  --library /absolute/path/NativeBridge.dylib \
  --password-file /absolute/private/path/server-password \
  --origin http://127.0.0.1:4097 \
  --model deepseek/deepseek-flash \
  --project-directory /absolute/path/ios-control-bridge
```

Replace all placeholder paths. Model and project directory are optional; the
model selection applies to the dedicated Siri conversation. The installer
preserves pre-existing tweak/job files and requires an explicit upgrade review.
It stages and signs a fresh file, then atomically replaces the target inode.
Never overwrite an already mapped signed dylib in place: an early development
installation hit a code-signing invalid-page failure using that approach.

The backend sets and reads back **its own** active/inactive 128 MiB process
limits using `memorystatus_control`. The initial launchd default caused a
per-process-limit termination at 18 MiB on the first HTTP call. No other
process's limit is adjusted. The struct/commands are defined in Apple's
[XNU memory-status header](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/kern_memorystatus.h).

The installer starts `dev.ioscontrol.siri` and restarts assistantd, keeping
routing **disabled**. Check for `bridge_ready` in `native-events.jsonl`, then:

```sh
python3 -B /absolute/path/integrations/siri/install.py enable
```

Enabling checks the installation hashes, native readiness event and backend
status. Unlock the phone and ask the original Siri a harmless question. Check
both the displayed answer and audible reply. A successful framework fixture
alone cannot prove UI appearance or sound.

## Disable and recovery

```sh
python3 -B /absolute/path/integrations/siri/install.py disable
```

This removes the owned enable flag. Subsequent requests use stock Siri. It does
not restart SpringBoard or undo a task already accepted by OpenCode. The running
backend can be stopped with `launchctl bootout system/dev.ioscontrol.siri` after
disabling routing. Keep the root state and OpenCode history for inspection.

Unsupported hook ABIs and a missing enable flag leave original request routing
in place. Once a request has been handed to OpenCode, an ambiguous result is
reported as unconfirmed and is not replayed through Siri. A missing socket allows
stock routing; a stale socket that fails to connect returns an availability
message for that intercepted turn.

`RequestObserver.m` and `NativeBridge.m` are development probes. Do not install
them alongside the production transport for a fresh installation. They are not
required by the adapter. The development observer was removed after verification;
the production transport started successfully and returned a native unlock reply
after assistantd restarted.
