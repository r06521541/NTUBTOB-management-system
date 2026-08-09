# TASK-060 Codex report

## Status and commits

- Status: `ready_for_review`
- Task base commit recorded by Work: `84b589129e85c17e7247014dee3e8eb1060f4c7a`
- Work planning commit / branch starting HEAD: `b3fbc82b57c484c085a9d21f25ff05ff6283ed61`
- Implementation commit: `97c8ddc1ced3af13d432de59494b59d9ba313e44`
- Branch: `codex/task060-atomic-phase-a-artifact`

`b3fbc82` contains the TASK-060 specification and DEC-065 on top of the task's recorded base. Codex
created the branch from that current planning commit and did not rewrite either Work commit.

## Delivered behavior

- The deterministic artifact now renders Alembic `base -> 0003` rather than assuming a separately
  stamped `0001` marker. One transaction creates the canonical `ntubtob.alembic_version` table,
  inserts exactly `0001_legacy_baseline`, applies `0002` and `0003`, and performs the two expected
  version updates.
- The existing `5s` transaction-local lock timeout and `60s` statement timeout remain in the exact
  artifact. There is one `BEGIN`, one `COMMIT`, no `IF NOT EXISTS`, upsert, marker deletion,
  destructive DDL, application DML, remote endpoint or credential text.
- Revision `0002` enables RLS on exactly the 13 new portal-data tables. It does not force RLS, create
  policies, or issue grants/revokes; Phase A application access therefore remains none.
- The static verifier now checks the canonical marker shape and baseline insert, exact version
  transitions, exact table/index/function/trigger/alter allowlists, exact RLS table set, forbidden
  policy/force/privilege statements, deterministic source equality and sidecar checksum.
- Mutation tests cover marker drift, wrong revisions, upsert/delete/truncate, missing/extra/wrong RLS,
  policy/force/grant, split transactions, checksum drift, unapproved CREATE statements, destructive
  SQL, remote text and revision-graph drift.
- Local fake PostgreSQL rehearsals cover clean no-marker execution, atomic rollback after an injected
  mid-migration failure, bounded lock failure followed by one full retry, and fail-closed handling of
  a pre-existing marker or portal object. The success path verifies revision `0003`, all 13 RLS flags,
  no forced RLS, zero policies, unchanged fake legacy row counts and no backfill/application rows.
- Hosted CI now starts the local fake fixture without `alembic stamp`, so Python 3.10 will exercise
  marker creation from an absent version table.
- Migration README, RLS decision package, production runbook and sanitized evidence template now
  describe the DEC-065 atomic marker and zero-policy RLS contract and require a fresh TASK-059 gate.

## Changed files

- `.github/workflows/python-tests.yml`
- `migrations/versions/0002_portal_data_foundation.py`
- `tools/portal_data_migration_readiness.py`
- `tests/portal_data/test_migration_readiness.py`
- `docs/operations/sql/portal-data-0001-to-0003.sql`
- `docs/operations/sql/portal-data-0001-to-0003.sql.sha256`
- `migrations/README.md`
- `docs/operations/data/PORTAL_DATA_RLS_DECISION_PACKAGE.md`
- `docs/operations/data/PORTAL_DATA_PRODUCTION_MIGRATION_RUNBOOK.md`
- `docs/operations/data/PORTAL_DATA_MIGRATION_EVIDENCE_TEMPLATE.md`
- `docs/coordination/reports/TASK-060-CODEX.md`
- `docs/coordination/HANDOFF.yaml`

## Verification performed

- Bundled Python portal-data suite against local fake PostgreSQL: 96/96 passed.
- Focused static artifact/verifier mutation suite: 9/9 passed.
- Deterministic artifact verifier: passed.
- Artifact static shape: one transaction; one marker create; one baseline insert; two exact version
  updates; 13 RLS enables; zero policies, force statements and grants/revokes.
- `python -m compileall -q tools migrations tests/portal_data`: passed.
- `isort --profile black --check-only` on the three changed Python files: passed.
- `docker compose -f docker-compose.portal-data.yml config`: passed.
- `git diff --check`: passed before the implementation commit and again before handoff.
- Task-started Compose container and network were stopped and removed after rehearsal; the pre-existing
  local fake-data volume was retained.

## Environment limitations

- The Windows `py -3.10` registration points to an unavailable Microsoft Store executable. Tests used
  the bundled runtime; hosted CI must provide the required Python 3.10 evidence.
- The bundled Black entry point did not return even for `--version`/single-file checks and was safely
  terminated. No dependency or environment modification was attempted. Source was kept in Black-style
  layout and isort passed, but Work/hosted CI should independently run Black.

## Safety confirmation

- No Owner CSV, production archive, credential/env file or secret was opened.
- No Supabase/remote/production query, baseline, migration, SQL execution or schema/data change occurred.
- Docker use was limited to repository-defined localhost PostgreSQL with conspicuously fake fixture data.
- No push, PR, merge, deployment, notification, Secret/IAM/Scheduler operation or external API occurred.

## Remaining risk and next gate

- Work must review the actual diff and commits, rerun sufficient tests and obtain hosted Python 3.10
  evidence after a separately authorized PR package.
- The local rehearsal proves deterministic transaction behavior against the fake catalog, not current
  production fingerprints, live lock duration, connectivity or execution-role behavior.
- After merge, Owner must rerun the exact TASK-059 read-only baseline and provide the sanitized CSV.
  Production execution remains prohibited until Work validates that fresh baseline and Owner approves
  the exact merged commit, SQL SHA-256, window, transaction and recovery boundary.
