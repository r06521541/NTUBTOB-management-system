# TASK-145B Notifications Codex report

- Base: `2b3233a014d70def812a7744efc58e802f5df7d0`
- Correction umbrella merged without rebase:
  `e25333565f7dad77d8bda8b0dc1cf4d663a24f24`
- Branch: `codex/task-145b-notification-read-model`
- Role: sole `codex-writer` for `task-145b-notification-read-model-writer`

## Delta

- Added immutable notification content plus principal recipient/read-state tables,
  fixed exactly 90-day visibility, deterministic `created_at/id` keyset order,
  RLS enablement and focused PostgreSQL integration coverage.
- Added principal-scoped list/detail/unread-count/mark-read/mark-all-read Mobile
  API and OpenAPI contracts. Other recipients and expired rows use the same 404;
  read mutations are atomic and idempotent.
- Added `notifications:read`, strict Flutter DTO/transport, installation+Person
  scoped cache and terminal-session purge. Identity/capability/session loss and
  corruption purge/fail closed; offline mode performs no mutation.
- Added a standalone notification-centre controller/widget and focused tests.
  Navigation/main composition remains deferred.

## Batched correction review

- Replaced every maximum/early-expiry interpretation with fixed 90-day schema,
  model, service DTO, OpenAPI and Flutter validation; early expiry now fails.
- Offline cache drops expired rows and recomputes its badge from the remaining
  unread items instead of replaying the old server count.
- Wired `NotificationCache` into real `BasicBootstrapApp`, terminal logout,
  terminal session purge and fresh Person/capability reconciliation. Focused
  tests prove explicit logout, terminal authorized 401 and Person change purge
  while retaining accepted 145A presentation behavior.
- Bounded notification path/DTO/cursor IDs to 32 characters and PostgreSQL's
  positive signed-bigint maximum before repository access.
- Added exact `0007_mobile_notifications` runtime readiness, tests and README.

## Verification

- `py -3.10 -m unittest discover -s apps/mobile_api/tests -v` with repository
  `shared_lib` on `PYTHONPATH`: 32 passed.
- `py -3.10 -m unittest tests.test_notification_api_service -v` from
  `shared_lib`: 6 passed.
- `py -3.10 -m unittest tests.portal_data.test_mobile_notifications -v` with
  both database URL variables explicitly cleared: 1 passed, 2 PostgreSQL tests
  skipped.
- Pinned `flutter test test/notification_center_test.dart test/basic_app_test.dart`:
  76 passed.
- Pinned `flutter analyze` on the five affected Dart implementation/test files:
  no issues.
- Pinned package-context Dart format check on `basic_app.dart`,
  `notification_center.dart` and both focused tests: 4 files, 0 changed.
- Per-file Python 3.10 Black fallback: all 10 affected Python files clean;
  `test_openapi_contract.py` was formatted once, then passed its check.
- Python 3.10 `compileall`, OpenAPI JSON parse and `git diff --check`: passed.

## Limits and external effects

- Local PostgreSQL 16 integration was not run: the existing Docker daemon probe
  timed out and no task-safe database URL was available. The tests remain
  default-skipped rather than connecting anywhere unknown.
- The authority `integration.dart` layout remains noncanonical under a full-file
  Dart 3.13 format check. Its correction diff is limited to semantic notification
  hunks, and those hunks match formatter output; unrelated authority layout was
  not reflowed.
- A heartbeat audit found no task-owned Python/Black process. The two long-lived
  10:23 Python processes belonged to a separate `polish-teaching-podcast`
  `pip install torch` lineage. After the writer was revoked, Main incorrectly
  attributed and terminated those two unrelated processes before reading this
  completed audit. This did not change this repository, but it interrupted that
  separate installation and may require it to be restarted.
- No deployment, staging/production database, Secret/IAM, provider, real data,
  notification delivery, publishing, notification push, PR, or runtime/data
  external effect occurred; only the requested Git branch push is planned.
