# TASK-122 Flutter Work review

status: accepted_pending_hosted_ci
reviewed_implementation: 6fcddee0177c742c561ee8bb31bc15f7c7211ed1
reviewed_by: Flutter Domain Work

## Scope and behavior

- The implementation changes only `clients/flutter_app/**` and the single
  `TASK-122-FLUTTER-CODEX.md` report.
- The real `BasicGamesView` diagnostic shows only a localized access role and
  the derived report-read enabled/disabled state. It does not expose identity,
  raw capabilities, endpoint, token, subject, session, storage or response
  data.
- Rendering is hard gated by `kDebugMode && diagnosticEnabled`; the injected
  flag can disable diagnostics for tests but cannot enable them in release.
- The existing `person.canReadAttendanceReport` route guard and navigation are
  unchanged. No capability, network, cache, mutation or notification behavior
  was added.

## Review rounds

1. Changes requested: the initial public `debugMode` override could render the
   projection when explicitly set in a release build.
2. Accepted: the render gate now contains the compile-time `kDebugMode`
   conjunction and a direct contract test proves an injected enable flag cannot
   override `debugBuild: false`.
3. Hosted CI changes requested: PR #133 run `32335100597` failed only the Dart
   formatter on `basic_app.dart` and `basic_app_test.dart`. The exact Flutter
   3.47 formatter changed only whitespace/line-wrap style in those files; this
   review accepted the correction at implementation SHA
   `74479ff7a1fff9033b01e50daa9f28cdfae8c3d5`.

## Verification and residual risk

- Implementer evidence: focused 33 tests, full 108 tests and `flutter analyze`
  passed; the exact two-file formatter check now passes; `git diff --check`,
  exact writer scope and changed-source sensitive scans passed.
- Domain review independently confirmed branch/origin equality, clean status,
  exact three-file scope, the hard release gate, all three localized roles,
  both report-read states, and the unchanged report guard/navigation.
- A fresh Android debug APK build remains unverified locally after the scoped
  Gradle wrapper made no bounded-window progress. Hosted Flutter analyze/test/
  debug-build evidence is required before merge.
- No staging build/install/cold start/login/runtime action occurred. After Main
  accepts and merges the source, the task's exact install-preserving-session
  runtime sequence remains separately gated.
