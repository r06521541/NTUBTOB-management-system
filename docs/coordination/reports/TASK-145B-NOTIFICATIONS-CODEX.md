# TASK-145B Notifications Codex report

- Base: `2b3233a014d70def812a7744efc58e802f5df7d0`
- Branch: `codex/task-145b-notification-read-model`
- Role: sole `codex-writer` for `task-145b-notification-read-model-writer`

## Delta

- Added immutable notification content plus principal recipient/read-state tables,
  90-day maximum visibility, deterministic content `created_at/id` keyset order,
  RLS enablement and focused PostgreSQL integration coverage.
- Added principal-scoped list/detail/unread-count/mark-read/mark-all-read Mobile
  API and OpenAPI contracts. Other recipients and expired rows use the same 404;
  read mutations are atomic and idempotent.
- Added `notifications:read`, strict Flutter DTO/transport, installation+Person
  scoped cache and terminal-session purge seam. Identity/capability/session loss
  and corruption purge/fail closed; offline mode performs no mutation.
- Added a standalone notification-centre controller/widget and focused tests.
  `basic_app.dart`, `main.dart` and navigation/composition were not modified.

## Verification

- `py -3.10 -m unittest discover -s apps\mobile_api\tests -v` — 31 passed.
- `py -3.10 -m unittest shared_lib.tests.test_mobile_api_service shared_lib.tests.test_notification_api_service -v` — 16 passed.
- `py -3.10 -m unittest tests.portal_data.test_mobile_notifications -v` —
  2 PostgreSQL tests skipped because no local test URL was present.
- `flutter test test\integration_test.dart test\notification_center_test.dart`
  through the pinned wrapper — 47 passed.
- `flutter analyze lib\integration.dart lib\notification_center.dart test\notification_center_test.dart`
  through the pinned wrapper — no issues.
- Package-context pinned Dart format/check on `notification_center.dart` and its
  focused test — no changes. Existing `integration.dart` layout was restored
  from authority after the pre-package formatter warning; its diff contains only
  notification semantic hunks.

## Limits and external effects

- Local PostgreSQL 16 integration was not run: the existing Docker daemon probe
  timed out and no task-safe database URL was available. The tests remain
  default-skipped rather than connecting anywhere unknown.
- `apps/mobile_api/revision_readiness.py` is outside the exact 145B write scope
  and still accepts only revisions 0005/0006. A later integration change must add
  exact 0007 readiness before a migrated runtime can serve requests; this branch
  does not bypass the fail-closed revision gate.
- No deployment, staging/production database, Secret/IAM, provider, real data,
  notification delivery, publishing, notification push, PR, or runtime/data
  external effect occurred; only the requested Git branch push is planned.
