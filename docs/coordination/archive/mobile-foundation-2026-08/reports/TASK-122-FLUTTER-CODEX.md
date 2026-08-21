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

## Staging runtime closeout

- Runtime source snapshot: accepted main
  `ff5dfd13da930226a8195f53e0c931f6c9d2fb31`, in a clean detached worktree.
- A first fresh debug APK had a different task-scoped debug signer, so it was
  retained only as task-local evidence and was never installed. A bounded
  task-scoped public-fingerprint comparison found one existing session-
  compatible debug signer in the TASK-115 Android user-home; no key material,
  password, or keystore location was recorded.
- Rebuilding the accepted snapshot with that existing signing environment
  produced a fresh staging debug APK with SHA-256
  `C83F7BE7239CBD90479AB78405E466EAB5D2130934415D16C17874DFC04FAA61`.
  The package was `tw.org.ntubtob.portal`, version `0.1.0`, debuggable, and its
  public signing fingerprint matched the installed session. `adb install -r`
  passed without clearing data or uninstalling.
- A single portal cold start showed the debug projection `幹部` and `報表讀取：啟用`;
  the guarded read-only attendance-report entry was present. The report list
  and a canonical empty report were read successfully without mutation or
  notification.
- With airplane mode enabled, a subsequent portal cold start showed the same
  Officer projection and an offline cached read-only report. Network was then
  restored. No report mutation control was enabled or used.
- After the Owner-provided restore-basic receipt, one portal cold start showed
  `一般使用者` and `報表讀取：停用`; the guarded report entry was absent. The fresh
  lifecycle evidence plus the accepted principal-reconciliation policy proves
  that an access-level downgrade clears the previous principal report cache;
  no storage read or report API/navigation was used for that check.
- One logout followed by one final portal cold start showed only the LINE login
  gate. The prior session, Basic presentation, Officer report entry, and cached
  report did not revive. Runtime terminal result: PASS.

### Runtime side effects and limits

- Allowed runtime effects were one staging APK replacement using `install -r`,
  portal-only stop/start cycles, one airplane-mode toggle restored to online,
  read-only report navigation, and one logout.
- No repository source changed during runtime; no re-login, attendance
  mutation, notification, raw response/body, token, provider subject, display
  name, or secure-storage value was read or retained.
- iOS runtime/signing remains deferred. The task-local mismatched-signer APK is
  retained only as non-secret diagnostic evidence; it was not installed.
