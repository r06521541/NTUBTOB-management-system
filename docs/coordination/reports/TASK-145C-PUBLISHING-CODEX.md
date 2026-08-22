# TASK-145C publishing implementation report

- Claim: `task-145c-notification-publishing-writer`, lease 1, actor `01a02766-813a-7333-a233-1ad01fd63353`.
- Base: `f6fb60bb3626964eb257a68fddc816b6e94f0c3c`; branch: `codex/task-145c-notification-publishing`.
- Delivery: exact `notifications:publish` authorization; server-expanded individual/game/team previews; recipient-count revision plus typed confirmation; atomic idempotent notification, recipient, immutable audit, in-app result and push-outbox commit; fake-only device lifecycle; rejecting provider seam; typed notification/game destinations with list fallback; and an Officer-only Flutter preview/confirm path. Basic receives no publishing entry or recipient preview and the client fails before transport without the exact capability.
- External boundary: no deploy, cloud, Secret/IAM, staging/database mutation, emulator, real token, real provider adapter or real notification was used. Push remains pending until the explicit rejecting adapter records the bounded retryable `provider_not_configured` result; in-app history is independent.

## Initial submission verification (`840c2d457919c6eddd495851b4d0d63b71bf628e`)

- Flutter focused tests: `flutter test test/basic_app_test.dart test/integration_test.dart test/notification_center_test.dart` — 122 passed.
- Flutter focused analysis: `flutter analyze lib/basic_app.dart lib/integration.dart test/basic_app_test.dart test/integration_test.dart` — no issues.
- Python focused unit/contract suite — 29 passed with 3 PostgreSQL integration tests skipped because `PORTAL_DATA_TEST_DATABASE_URL` was not available.
- Flask route suite: `apps.mobile_api.tests.test_app` — 15 passed using a temporary Flask 3.0.3 install.
- Affected Python compile and OpenAPI JSON parse passed; `git diff --check` passed.
- PostgreSQL-backed migration/atomicity evidence remains for hosted CI on the exact submitted HEAD. No local database was contacted.

## Batched review correction

The authoritative umbrella `73d1ec831f1d8d6d5e74c860b46a53b713517ace` was merged without rebasing or dropping the original implementation history. The three requested findings were corrected without scope expansion:

- Device register/revoke now locks the referenced `MobileSessionRecord` and verifies current active status, Person, session, installation hash and family expiry; registration also verifies platform. Revocation is limited to the exact current session. A partial unique index enforces one active owner per provider/token hash, and collisions or race-time integrity failures return only the bounded `device registration is unavailable` conflict.
- Flutter creates a cryptographically random command key after each successful preview. It retains that key across uncertain confirmation retries, clears it only when a new preview starts or publication succeeds, and therefore permits identical-content separate intents to publish independently.
- Typed destinations require exact key sets. Game identifiers use canonical signed PostgreSQL bigint bounds, including `-9223372036854775808`; extra keys, leading-zero, malformed and out-of-range values fall back to the notification list. OpenAPI applies `maxLength: 25` to each typed game identifier.

Correction verification intentionally covered only affected behavior:

- Flutter deep-link regression: 1 passed.
- Flutter Officer intent regressions: 2 passed (separate identical intents use different keys; uncertain retry reuses one key).
- Python publishing service/model/OpenAPI correction set: 9 passed.
- Focused Flutter analyze over the four affected Dart files: no issues.
- Affected Python compile, OpenAPI JSON parse and `git diff --check`: passed.
- The focused PostgreSQL device ownership test was collected but skipped because `PORTAL_DATA_TEST_DATABASE_URL` was unavailable. Hosted CI remains the database-backed gate; no local or remote database was contacted.

## Self-review and formatter note

Whole-file Dart formatting initially exposed the repository's known authority-layout mismatch and produced roughly 5,600 noisy changed lines across `basic_app.dart`, `integration.dart`, `basic_app_test.dart` and `integration_test.dart`. Before verification or commit, that formatter-only reflow was reverted to the base and the TASK-145C semantic hunks/tests were reapplied. The corrected four-file Dart delta is 544 insertions with no authority-layout deletion/reflow. Focused analysis and tests then passed.

The bundled Windows Black CLI/API repeatedly stalled as documented by the repository guidance, including on a single affected file, so it was terminated rather than allowed to normalize or block unrelated authority. Python compile, focused tests and diff checks passed; hosted CI remains the final formatter gate.

This implementation is self-reviewed and handed off for independent acceptance; the writer does not self-accept.
