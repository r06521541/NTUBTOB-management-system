# Flutter Basic native client

The development build remains a deterministic fake. Staging and production compose the Basic-only native LINE login and HTTP client only when all required compile-time configuration is present. Officer/Admin APIs, push/deep links, release signing, deployment, and real service configuration are intentionally absent.

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

Staging/production require `CLIENT_MODE=real`, an HTTPS `API_BASE_URL`, numeric
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

No release signing configuration is committed. Debug builds must use the explicit fake command above and must not contact LINE or an API.

## Verification gate

From this directory, run `flutter pub get`, `dart format --output=none --set-exit-if-changed .`, `flutter analyze`, `flutter test`, and the debug build with both fake defines. The fake repository remains fixed/injected and network-free. Real cached data is versioned/installation-partitioned, and offline behavior is read-only; attendance mutations are refused until online.
