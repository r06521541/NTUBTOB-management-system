# Flutter fictional foundation

This directory is a Flutter-local, deterministic preview only. It contains no endpoint, hostname, credential, token, secret, backend contract, platform push integration, or external network behavior.

## Flavors and platform generation

`AppFlavor` is an environment label only (`development`, `staging`, `production`). It does not select resources or credentials. Select it at compile time with `--dart-define=APP_FLAVOR=development`; an unknown value fails closed before the app starts.

Platform runners are intentionally absent because this worktree has no Flutter, Dart, or Android SDK. After the owner installs a compatible Flutter SDK and confirms Android/iOS prerequisites, generate only the runners from this directory with:

```sh
flutter create --platforms=android,ios --project-name ntubtob_fictional_client .
```

The expected additions are `android/`, `ios/`, and Flutter-generated metadata. Before accepting them, review `git status --short` and the complete diff; reject unrelated dependency, identifier, signing, resource, endpoint, or credential changes. Generation does not authorize building, signing, deployment, or store distribution.

## Verification gate

From this directory, run `flutter pub get`, `flutter analyze`, and `flutter test`. Until the SDK is installed by the owner, these commands are not executable in the current environment. The fake repository uses a fixed/injected UTC snapshot time, and its mutation method always fails closed to preserve offline read-only behavior.
