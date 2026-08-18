# Flutter fictional foundation

This directory is a Flutter-local, deterministic preview only. It contains no endpoint, hostname, credential, token, secret, backend contract, platform push integration, or external network behavior.

## Flavors and platform generation

`AppFlavor` is an environment label only (`development`, `staging`, `production`). It does not select resources or credentials. When the Flutter SDK is available, run `flutter create .` from this directory to generate platform runners; generated Android/iOS files are intentionally deferred because this worktree has no Flutter, Dart, or Android SDK.

## Verification gate

From this directory, run `flutter pub get`, `flutter analyze`, and `flutter test`. Until the SDK is installed by the owner, these commands are not executable in the current environment. The fake repository uses a fixed/injected UTC snapshot time, and its mutation method always fails closed to preserve offline read-only behavior.
