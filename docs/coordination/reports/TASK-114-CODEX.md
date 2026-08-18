# TASK-114 Codex report — Shared/Web Slice A

## Result

- Added request-time mobile capability projection from the fresh active Person
  principal. Basic retains `games:read` and self attendance reply only;
  Officer/Admin additionally receive the bounded `attendance:report:read` read.
- Added a shared attendance-report application projection that checks capability
  before resource lookup, then checks the Person-scoped visible Game before
  calling the existing bounded repository report. Basic cannot enumerate Game
  existence; missing, cancelled and otherwise invisible Games share 404.
- Added low-sensitive, stably ordered replied/not-attending/not-yet-replied
  cohorts with explicit history counts and thresholds. The DTO excludes Member
  IDs, identity subjects, contacts, admin notes and audit data.
- Added `/api/v1/games/{game_id}/attendance-report`, request-time `/me`
  capabilities, bounded query validation, canonical OpenAPI schemas/examples
  and checked JSON fixtures. Existing attendance mutation remains self-only and
  unchanged.

## Safety and boundary review

- No schema, migration, model, controlled SQL, Web role allowlist, Flutter,
  global coordination or production configuration changed. Revision remains
  exactly `0005_mobile_auth_api_foundation`.
- The report path calls only `scoped_game` and `game_attendance_report`; tests
  prove Basic denial occurs before either read and that the attendance mutation
  service is not called. No notification, external caller or write endpoint was
  added.
- Authentication still resolves the principal from persistent state on every
  request. Tests cover inactive/unlinked rejection and an Officer-to-Basic
  request-time downgrade.
- Existing repository observations are reused without inventing roster
  snapshots or historical eligibility. No repository SQL changed, so local
  PostgreSQL 15/16 integration was not required by the task.

## Verification

- Mobile API full offline suite: 19 passed.
- Shared library full offline suite: 25 passed, including the unchanged TASK-106
  attendance notification boundary tests.
- `py_compile` passed for all affected Python implementation and test modules.
- Black 24.4.2 formatter API comparison and isort 5.13.2 `--profile black`
  checks passed for all affected Python files.
- `git diff --check` passed. Final status is reported after commit/push.

## Unverified

- Hosted Python 3.10/final-gate execution remains for the integrated final PR.
- No browser/device, staging, production, database, LINE, Secret, IAM,
  notification, push, broadcast, deploy or external operation was performed.

## Handoff

- Branch: `codex/task-114-mobile-officer-readonly-parity`
- Base/task specification: `008b1a64dbee1db59223fd6329ae1f4169b16626`
- Accepted upstream main: `7ef79b1380ac054b867bcac0fd4b2c317b81d778`
- Report: `docs/coordination/reports/TASK-114-CODEX.md`
- Status/next actor: `ready_for_review` / Main Work after push; no PR created.
