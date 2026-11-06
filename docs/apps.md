# App installation and removal

`iosctl` 0.13.0 adds six fixed app operations. The native helper is
`build/native/icb-apps` (`ICB_APPS_HELPER` can select an explicit deployment).
Private signatures are checked at runtime; the current OS boundary is iOS
16.1.1 / 20B101. Build it with `python3 tools/build_native.py`.

| Operation | Parameters | Result |
| --- | --- | --- |
| `apps.list` | `query?`, `include_system?` (false), `limit?` (1–500, default 50), `offset?` | Installed app metadata, stable bundle IDs, `has_more`; no app data or account history. |
| `apps.get` | `bundle_id` | Fresh installed/placeholder state, version and protection status. |
| `apps.store_info` | Exactly one of `app_id` or `url` | Apple's catalog metadata and whether a free app offer is available in the device's store context. |
| `apps.install` | Absolute `path`, `bundle_id?`, `installer?`, `replace?`, `sha256?`, `max_bytes?`, `verify_timeout_ms?` | Install a local IPA, then independently check its bundle ID and build version. |
| `apps.download` | `source: "ipa"` plus HTTPS `url`, or `source: "app_store"` plus `app_id` / Apple `url` | Download and install; verified only after independent state readback. |
| `apps.uninstall` | Exact `bundle_id`, `installer?`, `verify_timeout_ms?` | Remove only that app; verify both the installed app and placeholder are absent. |

`apps.download` with `source: "ipa"` also accepts the optional install parameters
and `download_timeout_ms`. App Store accepts only its source/identifier,
optional expected `bundle_id` and `verify_timeout_ms`.

## Examples

Run commands on the phone through its existing terminal or authorized SSH
connection. Pass JSON as a single argument.

```sh
iosctl capabilities --service apps
iosctl call apps.list --params '{"query":"example","limit":20}'
iosctl call apps.get --params '{"bundle_id":"com.example.app"}'

# Apple ID and ordinary system confirmation remain in effect.
iosctl call apps.store_info --params '{"app_id":"1380911705"}'
iosctl call apps.download --params '{"source":"app_store","url":"https://apps.apple.com/app/id1380911705","verify_timeout_ms":60000}'

# System installation requires an IPA whose signing is accepted by this device.
iosctl call apps.install --params '{"path":"/var/mobile/Downloads/Example.ipa"}'
iosctl call apps.download --params '{"source":"ipa","url":"https://example.com/Example.ipa","bundle_id":"com.example.app"}'

# Optional: explicitly use an already installed TrollStore. Requires root.
sudo iosctl call apps.download --params '{"source":"ipa","url":"https://example.com/Example.ipa","installer":"trollstore"}'
sudo iosctl call apps.uninstall --params '{"bundle_id":"com.example.app","installer":"trollstore"}'

# Standard user apps use LaunchServices by default.
iosctl call apps.uninstall --params '{"bundle_id":"com.example.app"}'
```

The example domain is a placeholder: supply the actual IPA URL and bundle ID.
App Store IDs are numeric IDs, while deletion uses the app's bundle ID. Use
`apps.list` or `apps.store_info` to resolve the exact target first.

## Installation channels and verification

`installer` is `system` by default. `trollstore` explicitly delegates the fixed
install/uninstall command to the existing TrollStore app's `trollstorehelper`;
the bridge does not install TrollStore or switch installers after a refusal.
There is no arbitrary helper path or caller-selected selector. Existing apps
are not replaced unless the IPA request includes `replace: true`.

App Store uses `SSLookupRequest` with the `product` key profile, then
`SSPurchaseRequest` with the original free offer returned by Apple. Download,
installation-job creation and purchase validation are explicitly enabled. The helper
uses the interactive mobile user's store context. No synthetic price,
Apple ID credentials, version downgrade or paid purchase parameters are accepted.
Apple can show its normal installation, password or biometric confirmation.
Complete authentication on the phone; do not send credentials to the bridge.

An authentication prompt or queued download can outlive the bounded call.
The bridge starts a worker which retains the purchasing context for up to
10 minutes of authentication, with a hard lifetime of 11 minutes. The caller
receives a partial acknowledgement promptly; closing that CLI call does not
terminate authentication. A process-held per-app lease prevents a duplicate
request while the worker remains active. The worker exits after the transaction
callback and a short handoff period, or when its deadline expires.
`partial/store_download_pending` includes the target bundle ID and next step:
complete the system prompt, then query `apps.get`. **Do not submit the download
again merely because readback timed out.** An installed, non-placeholder app is
required for `verified`; request submission and callbacks alone are insufficient.
`apps.get` can also include the recent request's completion status and sanitized
system error domains/codes. A failed system request is reported as
`unavailable/store_request_failed`, rather than being left in a pending state.

IPA downloads require HTTPS, including every redirect. They stream to a private
temporary directory, enforce size/time limits, record SHA-256, and optionally
verify a supplied hash. URL credentials and fragments are rejected. Default
size limit is 512 MiB, configurable up to 2 GiB; download timeout defaults to
120 seconds, configurable from 1 to 600 seconds. Readback defaults to 15 seconds
and can be set from 0 to 120 seconds. Native calls also have bounded deadlines.

The IPA inspector checks a single top-level app manifest, bundle ID, executable,
version, bounded expansion, duplicate/traversal paths and escaping symlinks.
The installer receives a private copy because LaunchServices may consume its
input. Original local IPAs are preserved and failed downloads are cleaned up.
Signing and compatibility refusals are reported, not converted to success.

Uninstall accepts an exact bundle ID, never a name, query or wildcard. System
apps and apps outside the user app containers are protected. Already absent
targets return verified with `changed: false`; an IPC acknowledgement without
independent absence returns partial. A timeout never causes automatic replay.

For a remote command transport, allow enough execution time for download,
native installation and readback. If the caller disconnects, inspect `apps.get`
before attempting another write.

## References

The implementation uses independently written adapters, runtime signatures
observed on the device, and these upstream interface references:

- [AppSync's appinst](https://github.com/akemin-dayo/AppSync/blob/master/appinst/appinst.m): LaunchServices install/uninstall interfaces and IPA consumption behavior.
- [StoreServices runtime interfaces](https://github.com/nst/iOS-Runtime-Headers/tree/master/PrivateFrameworks/StoreServices.framework): catalog request and offer accessors.
- [StoreServices purchase request interface](https://github.com/nst/iOS-Runtime-Headers/blob/master/PrivateFrameworks/StoreServices.framework/SSPurchaseRequest.h): request validation and download creation.
- [TrollStore root helper](https://github.com/opa334/TrollStore/blob/main/RootHelper/main.m): the existing install/uninstall CLI contract.
