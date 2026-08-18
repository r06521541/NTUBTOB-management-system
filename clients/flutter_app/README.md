# Flutter Basic native client

The development build remains a deterministic fake. Staging and production compose the Basic-only native LINE login and HTTP client only when all required compile-time configuration is present. Officer/Admin APIs, push/deep links, release signing, deployment, and real service configuration are intentionally absent.

## Flavors and platform generation

Missing, empty, unknown, or mixed configuration fails before the app starts. Development must explicitly select isolated fake mode and must not receive service configuration:

```sh
flutter run --dart-define=APP_FLAVOR=development --dart-define=CLIENT_MODE=fake
```

Staging/production require `CLIENT_MODE=real`, an HTTPS `API_BASE_URL`, and numeric `LINE_CHANNEL_ID`, supplied by an approved local/runtime configuration mechanism. Never commit those values. Example placeholders are deliberately not provided because a launch must fail closed until real approved values exist.

Android and iOS runners were generated with Flutter 3.47.0. To reproduce them after installing a compatible Flutter SDK and confirming Android/iOS prerequisites, run from this directory:

```sh
flutter create --platforms=android,ios --project-name ntubtob_fictional_client .
```

The expected additions are `android/`, `ios/`, and Flutter-generated metadata. Before accepting regenerated files, review `git status --short` and the complete diff; reject unrelated dependency, identifier, signing, resource, endpoint, or credential changes. Generation does not authorize signing, deployment, or store distribution. iOS build and signing remain deferred to a macOS host with Xcode and CocoaPods.

## Session and platform boundary

Access tokens are memory-only. Refresh/session continuity, installation isolation, retry attempt IDs, pending mutations, and `logout_pending` use platform secure storage. Android backup is disabled and secure storage uses an isolated namespace without backup migration; iOS Keychain accessibility is `first_unlock_this_device`. Android requires API 24 and declares INTERNET in the main manifest. iOS target 15 configuration is reviewable here, while runtime/build/signing requires macOS/Xcode.

No release signing configuration is committed. Debug builds must use the explicit fake command above and must not contact LINE or an API.

## Verification gate

From this directory, run `flutter pub get`, `dart format --output=none --set-exit-if-changed .`, `flutter analyze`, `flutter test`, and the debug build with both fake defines. The fake repository remains fixed/injected and network-free. Real cached data is versioned/installation-partitioned, and offline behavior is read-only; attendance mutations are refused until online.
