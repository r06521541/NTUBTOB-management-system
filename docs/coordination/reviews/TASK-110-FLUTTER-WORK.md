# TASK-110 Flutter Work review

status: changes_requested
reviewer: flutter_domain_work
reviewed_at: 2026-08-18
branch: codex/flutter-basic-api-integration
implementation_commit: f396151b01f39984ec72087359e05f81bc745328

## Review result

TASK-110 remains under correction after Main Work review. The implementation preserves the fictional development composition while adding fail-closed staging/production configuration, native LINE ID-token exchange, installation-isolated session handling, canonical Basic API DTOs, paged games, game detail, replied-team attendance, and all five attendance replies.

Two correction rounds were required. The final source includes typed auth/account/session states, generation-aware single-flight refresh for concurrent 401 responses, terminal-session clearing, bounded native-login timeout, Android/iOS-only platform selection, durable logical-mutation idempotency and uncertain-result reconciliation, offline read-only behavior, explicit empty/error states, and Basic-only privacy.

Main Work subsequently identified one blocking transport-ambiguity path: an attendance PUT that throws `NetworkException` after dispatch is not reconciled through the authoritative attendance read and is shown as a generic mutation error. Acceptance is withdrawn until that path preserves the durable intent, reconciles when possible, and reports an uncertain outcome when it cannot prove the result.

## Evidence reviewed

- Implementation branch and origin both resolved to `f396151b01f39984ec72087359e05f81bc745328`; worktree was clean and writes stayed within the approved Flutter/report scope.
- Implementer evidence: `flutter pub get`, formatter, `flutter analyze`, 64 Flutter tests, and an explicit fake Android debug build passed.
- Debug APK SHA-256: `1ED5CC7EB1DFBAF74493CA3875EAA6F22C163561E8052A583C569B3A60C5048B`; the ignored artifact was not committed.
- Flutter Domain Work independently completed cumulative diff review, OpenAPI mapping review, writer-scope review, `git diff --check`, and Dart format check (`7 files`, `0 changed`).
- Domain Work attempts to rerun `flutter analyze` and `flutter test --no-pub` produced no output during Windows Flutter SDK startup and were terminated; they are not claimed as independent passing runs.
- Manifest, debug signing, dependency pins, tracked-artifact, endpoint, credential, and release-signing boundaries were reviewed with no blocking finding.

## Deferred and residual risk

No real LINE login, API traffic, emulator/device interaction, iOS build/runtime/signing, release signing, deployment, upload, Officer/Admin API, push, or deep-link integration was performed. The exact `flutter_line_sdk 2.7.2` pin still emits a future Kotlin migration warning, but the accepted debug build succeeds. Runtime staging evidence remains a later authorized work package.
