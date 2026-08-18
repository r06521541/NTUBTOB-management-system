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

- Added `ManagementReportReadGrant`, a typed local presentation input derived only when the fresh Person is Officer/Admin and contains the exact `attendance:report:read` capability. A Basic Person carrying that capability, or Officer/Admin without it, remains denied and performs zero report calls. Fictional `Persona` is never real authority.
- Added `RealModePresentationPolicy` and guarded UI route enum. Every principal retains the four Basic primary destinations; only a granted principal discovers the fifth management destination. Direct management/report access with no grant fails closed to home. Bottom navigation is always four or five destinations.
- Added exact typed `Person` access-level/capability parsing and the canonical attendance-report DTO hierarchy. The parser enforces required fields, UTC timestamp, reply enum, history-limit enum, response-rate bounds, and ten-point minimum-response-rate increments while retaining the established forward-compatible unknown-field policy.
- Added the exact read-only API call `GET /games/{game_id}/attendance-report` with canonical default query values (`history_limit=12`, `minimum_response_rate=60`). No Officer/Admin mutation method exists.
- Added explicitly UI-only attending, not-attending, and not-yet-replied cohorts behind a canonical adapter. Each unanswered Person retains all five canonical observation metrics; generated time and the complete history observation are displayed without client-invented values.
- Added a local presentation port and deterministic fake repository with all three cohorts and bounded observation data. Development fake composition remains unchanged.
- Added a versioned, bounded single-value durable report cache through the existing `DurableStore`; no dependency was added. It permits at most 20 reports, 200 people per report, and 65,536 UTF-8 bytes per principal blob, with internal limits of 256 characters for IDs, 300 for the local game label, and 120 for display names. Its key contains installation and principal, while each value is game-keyed and contains only low-sensitive report presentation data. Unknown version, corruption, invalid fields, or oversized reads are deleted and fail closed; oversized/invalid writes fail before `store.write` and preserve the prior valid blob. No refresh/access token, provider assertion, nonce, raw error, contact, admin note, or audit data is serialized.
- Real composition injects that durable cache. Fresh reconciliation compares both grant and ordered `AccessLevel`; identity change, admin→officer or any other role downgrade, capability revocation, 403, terminal session expiry, and logout purge the affected principal blob before route reuse. Officer→admin does not spuriously purge. Offline reconstruction still requires the last fresh server-derived Person to satisfy role plus exact capability, so Basic cannot read an Officer cache.
- Storage remains in the existing `SecureStore` namespace without moving or changing refresh/session token handling. Android keeps `migrateWithBackup: false`; iOS keeps `first_unlock_this_device`, binding Keychain availability to the current device. No new backup, dependency, or session-storage semantics were introduced.
- Added loading, empty, ready, retryable error, forbidden/resource-unavailable, session-expired, contract-error, and offline-cached read-only states with distinct Traditional Chinese semantics. Canonical 404 maps to non-leaking forbidden/unavailable, 422 and malformed/nonretryable contract errors settle into contract-error, and no Future remains stuck in loading. The controller exposes no mutation action, including offline.
- Integrated one guarded real-mode report entry into the existing Basic games shell. Basic sees no entry and a directly constructed route performs zero API reads; Officer/Admin are identical read-grant holders and receive no write/admin action. Existing games/detail/self reply and fictional development composition remain unchanged.

## Verification

- `flutter pub get`: passed using the existing exact lock.
- `dart format --output=none --set-exit-if-changed lib test`: passed, 9 files and 0 changes. Whole-tree formatting is unsuitable because ignored Gradle transform output may contain stale missing directories.
- `flutter analyze`: passed, no issues.
- `flutter test`: passed, all 97 tests after second review correction. The prior post-build invocation could not write its temporary compiler output because the failed Android build had exhausted C; after deleting only the exact task-local ignored `clients/flutter_app/build`, complete suites passed. No global cache was removed.
- Targeted coverage proves exact path/default query and DTO bounds, complete three-cohort/metric mapping and widgets, Basic/Officer/Admin role-plus-capability matrix, zero-call direct-route fail-closed, four/five bottom destination bounds, 404/422 settled states, durable restart/offline reconstruction, installation/principal isolation, corrupt/version/partial-write handling, encoded byte and field bounds, oversized-read deletion, oversized-write preservation, admin→officer purge, officer→admin retention, fresh/server downgrade/identity/session/logout purge, and zero mutation UI.
- Review-requested bounded `flutter build apk --debug --target-platform android-arm64 --dart-define=APP_FLAVOR=development --dart-define=CLIENT_MODE=fake`: invoked once. Flutter internally retried Gradle once after the first failure. Both phases failed with the same C-drive insufficient-space `IOException` while writing native merge/lint/download/diagnostic artifacts. No global cache was cleared and no second command was run. No current APK exists or checksum is claimed; hosted/fresh-disk CI remains the build evidence gate.
- Static review confirms the only new wire capability/path/fields are those from the accepted dependency SHA. There is no hostname, base URL, credential, Secret, token, LINE, notification, push, write method, or platform call in the Officer slice.
- `git diff --check` passed. No-secret/no-hostname/no-write-method scans found only the clearly fictional refresh-token test literal already used by the test harness and existing presentation notification labels; no credential or external endpoint exists. Final changed-file writer-scope, branch/HEAD/origin/status checks are recorded at delivery.

## Deferred contract boundary and side effects

- Officer and Admin are intentionally indistinguishable to this client slice: both can only arrive through the exact server-owned read capability. No write, Admin mutation, notification, broadcast, send, or hidden roster inference exists.
- No backend, OpenAPI, shared/schema/model/global coordination, staging/production, Secret, LINE, database, notification/push, deploy, PR, merge, or external service mutation occurred.
- External writes were limited to existing TASK-107 Flutter/Android/Gradle/pub caches and ignored local build output. A task-specific Git `safe.directory` entry was added due the worktree creator/execution SID mismatch; cleanup after retirement: `git config --global --unset-all safe.directory C:/Users/USER/Repos/NTUBTOB-management-system-flutter-task114`.
- Android APK packaging remains environment-unverified because of local disk exhaustion; hosted/fresh-disk CI can close this gate. iOS runtime, real staging/API/LINE invocation, and device smoke remain unverified/deferred. No real external call was made.
