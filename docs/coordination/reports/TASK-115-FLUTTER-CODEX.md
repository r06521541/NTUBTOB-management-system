# TASK-115 Flutter Codex Report

## Delivery

- Branch: `codex/task-115-flutter-staging-emulator`
- Base: `31435da5d616b499be02d9e54c8f8163e2569cc2`
- Scope: Flutter native LINE login lifecycle correction plus directly related tests.
- Repository writes are limited to the four approved Flutter source/test files and this report.

## Runtime finding

The API 36 Google Play x86_64 emulator showed one Android task containing, in order, the app `MainActivity`, one LINE SDK authentication activity, and one Chrome Custom Tab. It did not contain two LINE activities, two Custom Tabs, or two tasks. The prior client wrapped the entire native login future in a 35-second Dart timeout. That timeout returned control to retryable UI without cancelling the unresolved native flow, allowing a second attempt to be started while the first Chrome/SDK flow could still complete late.

Runtime inspection retained only redacted/task-specific evidence under `E:\codex-evidence\task-115`. No credentials, token, provider subject, secure-storage payload, raw response, or raw logcat was read or retained. No repository runtime artifact is committed.

## Correction

- Separates the observable 35-second UI timeout from settlement of the underlying native future.
- Tracks exactly one unresolved native attempt and rejects re-entry without a second SDK call.
- Ignores a late successful native result for exchange purposes; it only confirms that the native flow settled and permits a fresh attempt.
- Treats confirmed late cancellation as settled and retryable.
- Keeps stale/duplicate attempt checks fail closed and preserves exactly one exchange for the fresh successful attempt.
- Guards notifications after coordinator disposal.
- Adds a distinct Traditional Chinese timeout/unresolved state. The LINE login action is absent until the native flow confirms cancellation or completion.
- Keeps the authenticated UI transition owned by the subsequent `/me` and games load, avoiding a partially loaded authenticated view.

## Tests

Added deterministic coverage for:

- configured timeout while the native future remains unresolved;
- repeated login request during unresolved timeout producing zero additional native calls;
- late completion producing zero exchange;
- confirmed late cancellation permitting exactly one fresh native call;
- exactly one successful exchange on the fresh attempt;
- disposal before late completion producing no listener notification;
- existing stale/duplicate callback fail-closed behavior;
- timeout/unresolved widget semantics with no login action;
- confirmed cancellation restoring one login action.

## Verification

- `flutter pub get`: passed using the task-specific E-drive Pub cache.
- `dart format` on the four exact files: executed. Dart 3.13 proposed a repository-wide style reflow within those files (more than one thousand unrelated changed lines), so that mechanical output was removed and the focused existing style retained. This is a disclosed formatter limitation, not reported as a clean format check.
- `flutter analyze`: passed, no issues.
- `flutter test`: passed, 103 tests.
- `flutter build apk --debug --target-platform android-x64 --dart-define=APP_FLAVOR=development --dart-define=CLIENT_MODE=fake`: passed. The output remains ignored under `clients/flutter_app/build/` and is not committed or distributed.
- Final `git diff --check`, writer-scope, secret/credential, endpoint/config, and repository status checks are recorded at handoff.

Toolchain: Flutter 3.47.0, Dart 3.13.0, JDK 17.0.20, Android SDK reused from the approved task-specific E-drive toolchain. Gradle emitted the existing future Kotlin built-in migration warning for `flutter_line_sdk`; it did not fail the debug build and no dependency change was made.

## Deferred runtime acceptance

No LINE runtime attempt was started after source correction authorization. Runtime acceptance remains deferred until this commit is accepted and Main Work explicitly releases the TASK-116-ready staging gate.

The next single-attempt acceptance must:

1. Start from a confirmed closed/cancelled prior Custom Tab and settled app state.
2. Tap LINE login exactly once; Owner performs QR/login/consent without sharing credentials or token.
3. If the 35-second UI timeout appears, verify the login action stays absent while the existing native screen is unresolved.
4. After confirmed native completion/cancel, verify exactly one fresh retry becomes available.
5. On successful callback, verify fresh Basic data and only server-derived capability visibility, then perform the separately authorized staging read/offline/session checks.

No production, deployment, cloud, database, notification, push, release-signing, store, or authenticated staging mutation side effect occurred in this source-correction phase.
