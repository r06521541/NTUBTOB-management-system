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
- Invalidates the timed-out exchange generation immediately while retaining the independent native lifecycle lock.
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
- old callback completion during the unresolved window settling as stale with zero exchange while the native lock remains held;
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
- `flutter test`: passed, 104 tests after the stale unresolved-window correction.
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

## TASK-118 staging reacceptance and observability correction

The repaired fictional staging fixture was accepted before reacceptance. The original hidden-row timestamp defect caused the first two controlled `undecided` writes to remain unavailable to the public latest-reply readback; Main Work reconciled the authoritative prestate as `attending`. No credentials, token, provider subject, response body, storage payload, dynamic person name, or game content was retained during runtime acceptance.

After the fixture repair, one retained-intent `undecided` recovery submit completed without uncertainty. A portal-only cold restart and one first-game readback established the authoritative state as `undecided`. One fresh logical intent then restored `attending`; a second portal-only cold restart and one first-game readback established authoritative `attending`. All portal force-stops and launcher starts were explicitly authorized, package-scoped, and did not clear data or touch LINE.

Runtime inputs for the accepted repaired sequence were bounded to: one retained-intent recovery submit, one portal cold restart/readback, one fresh `attending` selection and submit, and one final portal cold restart/readback. No retry beyond the explicit retained-intent recovery, no login, no notification/push action, and no additional fictional mutation occurred. The final detail UI was ready, `attending` was selected after cold readback, and no loading, generic error, contract error, session-terminal, uncertainty, mutation error, or notification status was surfaced. Portal remained MainActivity-only with no ANR.

Runtime also exposed a Flutter observability defect: `GameDetailPage._submit()` fetched authoritative attendance after a successful reply but did not apply `loaded.ownReply` to the selected ChoiceChip, so the in-process post-submit selection remained only a local desired value. The minimal correction now assigns `selected = loaded.ownReply` in the successful readback state update. A widget regression test queues a server readback that differs from the local selection and verifies the authoritative reply overrides it; the uncertain path remains unchanged.

## Final runtime gates and verification update

- The source correction was verified with `flutter pub get`, `flutter analyze`, the focused `flutter test test/basic_app_test.dart` (30 tests), and full `flutter test` (105 tests); all passed with Flutter 3.47.0 / Dart 3.13.0.
- The scoped `dart format --output=none --set-exit-if-changed lib/basic_app.dart test/basic_app_test.dart` check was executed but reports pre-existing-style reflow in both files. No formatter output was applied, so it is not claimed as a clean formatter gate.
- A new development fake Android debug build was attempted using the task-specific E-drive toolchain. Its current Gradle wrapper (`assembleDebug`) made no observable progress beyond the bounded window and was terminated as the only build process. No new APK was created; the existing APK remained the earlier accepted artifact and is not evidence for this source correction. Android build is therefore **unverified** for this commit, rather than passed.
- Offline/cache runtime gate: airplane mode was enabled on `emulator-5556`, then the portal was cold-started once. It rendered the static offline read-only labels and exposed zero clickable controls; no navigation or mutation occurred. After network restoration, the authenticated shell recovered with its single logout action available.
- Logout/cache-purge runtime gate: the logout action was tapped exactly once, followed by one package-scoped portal cold restart (no data clear and no LINE action). The cold app presented only the LINE login action; Basic navigation, Officer/management/report UI, offline cache, and prior authenticated session were absent. `MainActivity` was the only relevant activity and no ANR was observed.

Runtime side effects were confined to the approved fictional staging account/game sequence, package-scoped portal stop/start operations, temporary emulator airplane-mode toggling, and one logout. There was no production access, deployment, cloud or database mutation, real notification/push, release signing, store action, credential/token/provider-subject access, raw payload/log retention, or repository runtime artifact.

Deferred: a fresh Android debug artifact for this source-only observability correction requires a later clean Gradle/hosted build. iOS runtime/signing remains outside this Windows/emulator task.
