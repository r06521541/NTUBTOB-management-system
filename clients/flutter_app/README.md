# Flutter Basic native client

The development build remains a deterministic fake. Staging composes the
Basic-only native LINE login and HTTP client only when all required compile-time
configuration is present. The only Android distribution channel is the bounded
`android-closed` Closed Testing candidate described below. Production runtime,
Officer/Admin APIs, push/deep links, deployment, and real service configuration
remain outside this repository contract.

## Flavors and platform generation

Missing, empty, unknown, or mixed configuration fails before the app starts. Development must explicitly select isolated fake mode and must not receive service configuration:

```sh
flutter run --dart-define=APP_FLAVOR=development --dart-define=CLIENT_MODE=fake
```

This command opens a clearly labelled fictional, production-shaped demo. Its
in-app controls switch between Basic/Officer, online/offline, and
populated/empty/error scenarios. The game list, game detail, attendance,
account-data status, and Officer report are the current production widgets fed
by deterministic in-memory adapters. Fake mode needs no account or credentials,
does not call LINE or an API, and does not use platform secure storage.

Staging/production runtime compositions require `CLIENT_MODE=real`, an HTTPS `API_BASE_URL`, numeric
`LINE_CHANNEL_ID`, `GOOGLE_CLIENT_ID`, and `GOOGLE_SERVER_CLIENT_ID`, supplied by
an approved local/runtime configuration mechanism. Android uses the Web server
client ID for backend tokens. iOS requires its iOS client ID plus that same Web
server client ID. Never commit real IDs or credentials.

iOS additionally resolves `GOOGLE_REVERSED_CLIENT_ID` from the gitignored
`ios/Flutter/AuthConfig.xcconfig`; use `AuthConfig.xcconfig.example` only as the
key-name template. For real builds it must be the exact reversed form of the
same iOS `GOOGLE_CLIENT_ID` supplied through `DART_DEFINES`; the iOS and Web
server client IDs must be distinct. The Xcode build phase rejects missing,
unresolved, mismatched, or malformed values while preserving the existing LINE
scheme. A clean development/fake build requires no Owner OAuth values and
rejects any Google configuration instead of falling back to it. A
macOS/Xcode build remains mandatory evidence; no Firebase plist is required.

Android and iOS runners were generated with Flutter 3.47.0. To reproduce them after installing a compatible Flutter SDK and confirming Android/iOS prerequisites, run from this directory:

```sh
flutter create --platforms=android,ios --project-name ntubtob_portal --org tw.org.ntubtob .
```

The expected additions are `android/`, `ios/`, and Flutter-generated metadata. Before accepting regenerated files, review `git status --short` and the complete diff; reject unrelated dependency, identifier, signing, resource, endpoint, or credential changes. Generation does not authorize signing, deployment, or store distribution. iOS build and signing remain deferred to a macOS host with Xcode and CocoaPods.

## Session and platform boundary

Access tokens are memory-only. Refresh/session continuity, installation isolation, retry attempt IDs, pending mutations, and `logout_pending` use platform secure storage. Android backup is disabled and secure storage uses an isolated namespace without backup migration; iOS Keychain accessibility is `first_unlock_this_device`. Android requires API 24 and declares INTERNET in the main manifest. iOS target 15 configuration is reviewable here, while runtime/build/signing requires macOS/Xcode.

For Android staging evidence, the existing `Invoke-MobileStaging.ps1` artifact
gate reads the APK package identity and signer certificate fingerprint and
compares them with the Owner-approved allowlist; it never creates a keystore or
handles a signing password.

### Android Closed Testing release contract

Every Android `release` task is fail closed. A real candidate must use package
`tw.org.ntubtob.portal`, API 36, `MOBILE_RELEASE_CHANNEL=android-closed`, and the
exact Dart contract `RELEASE_CHANNEL=android-closed`, `APP_FLAVOR=staging`,
`CLIENT_MODE=real`, and `RELEASE_SCOPE=basic`. Production, development, fake,
Officer/Admin, unknown, duplicate, missing, or additional Dart configuration is
rejected before compilation.

The approved staging origin and provider IDs must enter only through the
approved non-echoing external configuration mechanism; do not put them in Git,
documentation, a command line, or retained logs. The build compares the actual
HTTPS origin with `MOBILE_RELEASE_STAGING_API_ORIGIN_SHA256`, a lowercase digest
approved for the isolated staging runtime. The generated public contract asset
also requires `MOBILE_RELEASE_STAGING_PROVIDER_CONFIG_SHA256`, calculated from
the exact LINE, Android Google, and Web server Google IDs joined in that order
with LF separators and no trailing LF. The asset contains only these two
digests, never the origin or provider IDs. This rejects a mixed staging API and
provider configuration without retaining those identifiers.

The pubspec version name/code, `MOBILE_RELEASE_VERSION_NAME`, and
`MOBILE_RELEASE_VERSION_CODE` must agree. The current code must also be greater
than the canonical non-negative `MOBILE_RELEASE_PREVIOUS_VERSION_CODE` obtained
from the exact package's Closed Testing history (`0` is allowed only when the
package is verified to have no previous version). Any rebuild with a new
version or configuration is a new artifact and requires fresh inspection.

Signing is injected from a repository-external JKS/keystore using
`MOBILE_RELEASE_KEYSTORE_PATH`, `MOBILE_RELEASE_KEY_ALIAS`, and privately
supplied store/key passwords. The repository neither creates nor retains that
key. Before upload, `python -m tools.mobile_release inspect-aab` must be run in
`android-closed` mode with the exact package, version, previous version, staging
origin/provider digests, and approved upload-certificate SHA-256. Its single JSON result
binds the AAB byte hash/size, channel, Basic-only staging contract, API levels,
version transition, and signer fingerprint without printing the endpoint,
provider IDs, keystore path, alias, or password. Rebuilding after acceptance
invalidates that evidence.

Inspection requires JDK 17 and the repository's fixed Gradle wrapper. It runs
the pinned bundletool runtime strictly in offline mode: bundletool first
validates the complete App Bundle (including `BundleConfig.pb`), then dumps the
protobuf manifest used to establish the actual package, version name/code, and
minimum/target/compile SDK values. APK-only analyzers are not accepted for an
AAB. The caller artifact is copied once into a bounded private snapshot; bundle
validation, manifest metadata, archive checks, byte hash, and all signer checks
read only that same snapshot. Mutation of the original path after snapshotting
cannot change the accepted evidence.

No release signing configuration is committed. Debug builds must use the explicit fake command above and must not contact LINE or an API.

## Verification gate

From this directory, run `flutter pub get`, `dart format --output=none --set-exit-if-changed .`, `flutter analyze`, `flutter test`, and the debug build with both fake defines. The fake repository remains fixed/injected and network-free. Real cached data is versioned/installation-partitioned, and offline behavior is read-only; attendance mutations are refused until online.
