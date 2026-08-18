# Flutter fictional foundation

This directory is a Flutter-local, deterministic preview only. It contains no endpoint, hostname, credential, token, secret, backend contract, platform push integration, or external network behavior.

## Flavors and platform generation

`AppFlavor` is an environment label only (`development`, `staging`, `production`). It does not select resources or credentials. A missing, empty, or unknown value fails closed before the app starts. Launch each explicit local flavor with:

```sh
flutter run --dart-define=APP_FLAVOR=development
flutter run --dart-define=APP_FLAVOR=staging
flutter run --dart-define=APP_FLAVOR=production
```

Android and iOS runners were generated with Flutter 3.47.0. To reproduce them after installing a compatible Flutter SDK and confirming Android/iOS prerequisites, run from this directory:

```sh
flutter create --platforms=android,ios --project-name ntubtob_fictional_client .
```

The expected additions are `android/`, `ios/`, and Flutter-generated metadata. Before accepting regenerated files, review `git status --short` and the complete diff; reject unrelated dependency, identifier, signing, resource, endpoint, or credential changes. Generation does not authorize signing, deployment, or store distribution. iOS build and signing remain deferred to a macOS host with Xcode and CocoaPods.

## Verification gate

From this directory, run `flutter pub get`, `dart format --output=none --set-exit-if-changed .`, `flutter analyze`, and `flutter test`. The fake repository uses a fixed/injected UTC snapshot time, and its mutation method always fails closed to preserve offline read-only behavior.
