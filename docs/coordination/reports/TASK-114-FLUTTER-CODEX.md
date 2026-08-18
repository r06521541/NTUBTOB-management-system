# TASK-114 Flutter Codex report

## Execution checkpoint and scope

- Goal: deliver the Flutter Officer/Admin read-only attendance-report slice without changing Basic mutation behavior.
- Core files: Flutter integration DTO/API, real/fake read-only presentation module, Basic route shell, tests, and this report.
- Invariants: authority comes only from fresh server-owned `attendance:report:read`; fictional `Persona` never authorizes real mode; Basic cannot discover or directly reach the report; offline never enables mutation.
- Minimum evidence: exact wire/query/parser tests, grant/navigation/direct-route tests, state/cohort/cache/downgrade tests, full Flutter gates, fake debug APK, and security/scope/diff scans.
- Ambiguity/blocker: none after accepted canonical artifact `9ed270d3c573885c096335140415b004ef867d22` was released and read in full with `git show`.

Work began clean on `codex/task-114-flutter-officer-readonly` at `008b1a64dbee1db59223fd6329ae1f4169b16626`.

## Canonical dependency and delivered slice

Canonical dependency: accepted backend artifact branch `codex/task-114-mobile-officer-readonly-parity`, full SHA `9ed270d3c573885c096335140415b004ef867d22`. No backend commit was checked out or cherry-picked. The accepted OpenAPI, checked fixtures, planning contract, report, and relevant route/contract/service tests were read from that object database only.

- Added `ManagementReportReadGrant`, a typed local presentation input that contains only a grant boolean. It has no capability wire name and does not inspect fictional `Persona`.
- Added `RealModePresentationPolicy` and guarded UI route enum. Every principal retains the four Basic primary destinations; only a granted principal discovers the fifth management destination. Direct management/report access with no grant fails closed to home. Bottom navigation is always four or five destinations.
- Added exact typed `Person` access-level/capability parsing and the canonical attendance-report DTO hierarchy. The parser enforces required fields, UTC timestamp, reply enum, history-limit enum, response-rate bounds, and ten-point minimum-response-rate increments while retaining the established forward-compatible unknown-field policy.
- Added the exact read-only API call `GET /games/{game_id}/attendance-report` with canonical default query values (`history_limit=12`, `minimum_response_rate=60`). No Officer/Admin mutation method exists.
- Added explicitly UI-only participant, single-game report, and non-responder-insight view models behind a canonical adapter, keeping wire DTOs separate from presentation models.
- Added a local presentation port and deterministic in-memory fake repository. The fixture includes one replied cohort, one not-yet-replied cohort, and a high-frequency non-responder display slot. Development fake composition remains unchanged.
- Added a principal-scoped in-memory report cache and controller. Fresh grant downgrade, identity change, server forbidden, or session expiry revokes management/report routes and clears the affected principal cache.
- Added loading, empty, ready, retryable error, forbidden, session-expired, and offline-cached read-only states with distinct Traditional Chinese semantics. The controller and shell expose no mutation action and report `mutationsEnabled == false`, including offline.
- Integrated one guarded real-mode report entry into the existing Basic games shell. Basic sees no entry and a directly constructed route performs zero API reads; Officer/Admin are identical read-grant holders and receive no write/admin action. Existing games/detail/self reply and fictional development composition remain unchanged.

## Verification

- `flutter pub get`: passed using the existing exact lock.
- `dart format --output=none --set-exit-if-changed lib test`: passed, 9 files and 0 changes. Whole-tree formatting is unsuitable because ignored Gradle transform output may contain stale missing directories.
- `flutter analyze`: passed, no issues.
- `flutter test`: passed, all 87 tests after canonical integration.
- Targeted coverage proves exact path/default query and DTO bounds, server-owned Basic/Officer/Admin grant mapping, grant-only discovery, zero-call direct-route fail-closed, four/five bottom destination bounds, deterministic cohorts/insight, all required states, offline read-only behavior, fresh/server downgrade revocation and cache purge, identity-change purge, and no write UI.
- `flutter build apk --debug --target-platform android-arm64 --dart-define=APP_FLAVOR=development --dart-define=CLIENT_MODE=fake`: attempted twice after canonical integration. Both attempts failed during Gradle dependency/plugin transformation because drive C had insufficient space (`IOException` in Gradle transforms). The exact task-local ignored `clients/flutter_app/build` directory was safely removed between attempts; the second attempt reproduced the same environmental failure. No current APK exists, so no artifact checksum is claimed. The earlier prereview APK predates canonical integration and is explicitly not delivery evidence.
- Static review confirms the only new wire capability/path/fields are those from the accepted dependency SHA. There is no hostname, base URL, credential, Secret, token, LINE, notification, push, write method, or platform call in the Officer slice.
- `git diff --check` passed. No-secret/no-hostname/no-write-method scans found only the clearly fictional refresh-token test literal already used by the test harness and existing presentation notification labels; no credential or external endpoint exists. Final changed-file writer-scope, branch/HEAD/origin/status checks are recorded at delivery.

## Deferred contract boundary and side effects

- Officer and Admin are intentionally indistinguishable to this client slice: both can only arrive through the exact server-owned read capability. No write, Admin mutation, notification, broadcast, send, or hidden roster inference exists.
- No backend, OpenAPI, shared/schema/model/global coordination, staging/production, Secret, LINE, database, notification/push, deploy, PR, merge, or external service mutation occurred.
- External writes were limited to existing TASK-107 Flutter/Android/Gradle/pub caches and ignored local build output. A task-specific Git `safe.directory` entry was added due the worktree creator/execution SID mismatch; cleanup after retirement: `git config --global --unset-all safe.directory C:/Users/USER/Repos/NTUBTOB-management-system-flutter-task114`.
- Android APK packaging is unverified after canonical integration because of local disk exhaustion; hosted/fresh-disk CI can close this environmental gate. iOS runtime, real staging/API/LINE invocation, and device smoke remain unverified/deferred. No real external call was made.
