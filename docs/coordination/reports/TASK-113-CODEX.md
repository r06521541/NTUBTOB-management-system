# TASK-113 Codex report — Cloud Build logging contract correction

## Result

- Added `options.logging: CLOUD_LOGGING_ONLY` to the staging-only Cloud Build
  configuration so its user-specified build service account uses a supported
  log destination.
- Added a static contract test that requires the exact Cloud Logging mode and
  rejects accidental `GCS_ONLY` or `logsBucket` configuration.
- Corrected the approved staging data operator for a truly empty dedicated
  PostgreSQL database. It now validates the empty state, executes the existing
  repository legacy fixture, stamps 0001 and upgrades through exact 0005 on one
  injected connection before seeding and exact readback.
- Added read-only recovery states for empty, exact migration-ready and completed
  fixtures. Unknown tables/rows, partial IDs, revision drift and legacy backfill
  drift fail closed without blind retry; database errors are redacted.
- Kept ordinary Alembic CLI execution localhost-only. Only an Alembic Config
  carrying an already identity-approved connection can use the remote path.

## Safety review

- Scope is limited to the staging Cloud Build static configuration, approved
  staging data operator/Alembic injected-connection boundary, their direct
  tests/runbook and this report.
- No production build configuration, migration revision, model, controlled SQL,
  service account, IAM, Secret, LINE, application behavior or global
  coordination file changed.
- No `gcloud`, build, deployment, database, Secret, IAM, LINE or other external
  operation was performed.

## Verification

- `python -m unittest tools.tests.test_mobile_staging_operator`: 17 tests,
  passed with 3 PostgreSQL integration tests skipped when their explicit URL
  was absent.
- PostgreSQL 16.2 true-empty integration: 3 tests passed, covering canonical
  bootstrap/seed/readback/cleanup, unknown-row rejection and transaction
  rollback after an injected migration failure. The isolated UTF-8 cluster was
  stopped and removed afterward.
- PostgreSQL 15 was not available locally and Docker Desktop's daemon was not
  reachable, so PG15 remains for hosted CI/Main Work verification; it was not
  claimed as passed.
- `python -m py_compile migrations/env.py tools/mobile_staging_data.py
  tools/tests/test_mobile_staging_operator.py`: passed.
- `python -m isort --profile black --check-only ...`: passed after applying
  import-only formatting to the two changed tool modules.
- Black 24.4.2 per-file check remained stuck in the documented bundled Windows
  failure mode and was terminated; hosted CI must provide the final Black
  evidence. `git diff --check` passed.

## Handoff

- Branch: `codex/mobile-staging-activation`
- Base/task specification: `a1814cf02abaf7650b72546e829cc43ae1ef8201`
- Report: `docs/coordination/reports/TASK-113-CODEX.md`
- Status/next actor after push: `ready_for_review` / Main Work; no PR created.
