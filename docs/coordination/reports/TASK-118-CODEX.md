# TASK-118 Codex report — staging attendance fixture repair

## Result

- Changed only the three TASK-112 fictional attendance reply timestamps to the
  deterministic past value `2000-01-01T00:00:00Z`; future Game dates and other
  fixture timestamps remain unchanged.
- Added a dedicated read-only inspection and candidate-approved repair path.
  It accepts only the original three fixture replies at the legacy 2035
  timestamp plus exact reply IDs `1` and `2` as `undecided` rows for Person/Game
  `-112001` with null legacy ownership and bounded timestamps.
- The repair transaction deletes only the two inspected row IDs, updates only
  the three fixture reply timestamps, performs an exact postcheck, and is a
  zero-delta success when retried after completion. Any count/content/timestamp
  drift fails closed.
- Updated the operator runbook with inspect, execute, uncertain-result recovery
  and no-blind-retry boundaries.

## Safety review

- Revision remains `0005_mobile_auth_api_foundation`; no schema, migration,
  model, Flutter, production, Secret, IAM, LINE or notification code changed.
- No staging/production database, cloud service, external API or Secret was
  accessed. PostgreSQL evidence used disposable local clusters only, which were
  stopped and removed.
- The repair cannot select arbitrary rows: fixture IDs and full stored shape are
  fixed, hidden rows must be exact IDs `1` and `2` with the proven
  Person/Game/reply/null-owner shape, and all changes occur in one transaction.

## Verification

- Staging seed/operator offline: 25 tests passed, 9 skipped without an explicit
  PostgreSQL URL.
- PostgreSQL 16.2 true-empty/fixture integration: 9 tests passed, including
  bootstrap, deterministic timestamp, exact repair, retry, drift rejection and
  runtime reply precedence.
- PostgreSQL 16.2 mobile foundation integration: 8 tests passed, including
  exact/concurrent same-key idempotency and finalize/reconcile paths.
- Mobile API offline: 25 tests passed. Shared library offline: 28 tests passed.
- `py_compile` and isort checks passed. Black 24.4.2 per-file check remained
  stuck in the documented bundled-Windows failure mode and was terminated;
  hosted CI must provide final Black evidence.
- PostgreSQL 15 was unavailable locally and Docker Desktop's daemon was not
  available; PG15 remains for hosted CI/Main Work verification.

## Handoff

- Branch: `codex/task-118-staging-attendance-implementation`
- Base/spec: `83884ba9f9d80ba9049102c1ec2fa8dc568bfe4c`
- Status/next actor after push: `ready_for_review` / Main Work
- No PR, deployment or external mutation was performed.
