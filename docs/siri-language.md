# Siri language and Mandarin/English speech

The optional Siri adapter receives **recognized text**. It does not replace
Apple's speech recognizer or receive the original audio. It preserves Chinese,
Latin text and Unicode when forwarding that text to OpenCode. Words missing or
misrecognized upstream cannot be recovered reliably by changing the chat model.

On 2026-11-06 the owner reported mixed Mandarin/English input problems. A fresh
mobile-user `AFPreferences` read confirmed the effective Siri language was
`en-US`. An earlier preference-file snapshot had shown `zh-CN`; a later live read
and file snapshot both showed English. That observation does not establish which
component changed the preference. System preferred languages and active keyboard
dictation languages are separate readings and do not establish Siri's language.

The owner specified Mandarin as the primary spoken language. The new fixed
`iosctl` adapter set Siri to `zh-CN` through `AFPreferences.setLanguageCode:` and
`synchronize`, with the measured 20B101 Objective-C ABI. A fresh process confirmed
`zh-CN`. No raw preference files were written, no language-selection flags were
changed, and no microphone capture or screen-control session was started by the
maintenance command.

The first immediate native read still returned the previous language. A later
process observed the completed change. The helper now allows a bounded two-second
settling window. The adapter additionally checks a new process, retries only
**reads** for a delayed update and never repeats the write. A cached acknowledgement
cannot establish success.

## Fixed operations

```sh
python3 -B bin/iosctl call siri.language.get
python3 -B bin/iosctl call siri.language.set --params '{"language_code":"zh-CN"}'
```

Only `zh-CN` and `en-US` writes are implemented. Both operations require the
verified iOS 16.1.1 / 20B101 device and the signed native helper. A root caller
launches the helper as `mobile` through fixed sudo arguments; the helper refuses
other UIDs. The existing native build tool produces `build/native/icb-siri-language`.
The macOS `build-siri` artifact also includes the executable as `LanguageSettings`.
Sign it with `native/siri/language-entitlements.plist` before installation.

The default installed helper path is
`/var/jb/usr/local/bin/icb-siri-language`. It must be executable and traversable
by mobile. `ICB_SIRI_LANGUAGE_HELPER` can select another explicit accessible path.
Stage and sign a new inode before atomically replacing an existing executable.

The result includes before/requested/readback values and an
`independent_readback` only after confirmation. Missing helpers, unsupported
builds and mismatched reads remain unavailable or partial. These operations are
client-neutral and do not require OpenCode or an AI account.

## Verification scope

The language setting and fresh-process readback passed on the device. Nine new
boundary tests cover invalid arguments, unsupported builds, bad native responses,
timeouts, stale values and delayed preference updates; all 160 portable tests pass.
The stock Siri mixed-speech test is awaiting the owner's post-change result.

Mandarin as the main language may help with Mandarin sentences containing English
names. This setting change does not establish arbitrary bilingual speech support.
An independent multilingual ASR path would be a separate feature with its own
audio, model and device validation. The original Siri interface remains in use.
