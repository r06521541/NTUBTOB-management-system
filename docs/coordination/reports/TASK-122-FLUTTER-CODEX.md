# TASK-122 Flutter Codex Report

## Delivery

- Branch: `codex/task-122-flutter-principal-observability`
- Base: `ddc86bedf3d0e9e76d964d69288df0d0cb4de340`
- Scope: debug-only, real `BasicGamesView` principal projection and direct tests.

## Implementation

- Adds a hard `kDebugMode && diagnosticEnabled` render gate to the existing
  real games view. The injected flag can disable the diagnostic in tests, but
  cannot override compile-time release absence.
- The diagnostic contains only the localized role (`一般使用者`, `幹部`, or
  `系統管理者`) and a localized derived `報表讀取：啟用／停用` value.
- It does not render a principal ID, display name, raw capability data, origin,
  endpoint, token, subject, session, storage, or response payload.
- Existing report guard/navigation remains `person.canReadAttendanceReport` and
  no network, cache, mutation, notification, or capability behavior changed.

## Verification

- `flutter pub get`: passed.
- Direct `flutter test test/basic_app_test.dart`: passed (33 tests), including
  the role/report-read matrix, unchanged-guard test, and a hard release gate
  test proving an injected enable flag cannot override `debugBuild: false`.
- `flutter analyze`: passed with no issues.
- Full `flutter test`: passed (108 tests).
- Hosted CI for PR #133 (run `32335100597`) reported only the two scoped Dart
  files as unformatted. Dart 3.13 / Flutter 3.47 formatting was then applied
  only to those files; the resulting diff is whitespace/line-wrap style only.
  The exact formatter check now passes.
- A development fake Android debug build was attempted without install or
  launch. Its TASK-122 Gradle wrapper made no bounded-window progress and
  produced no APK, so only that wrapper process was terminated. The build is
  unverified rather than passed.

No staging build, install, cold start, login, or runtime action is part of this
source phase. Final diff, writer-scope, and sensitive-literal checks are
recorded at handoff.
