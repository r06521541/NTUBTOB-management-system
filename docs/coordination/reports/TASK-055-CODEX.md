# TASK-055 Codex report

## Status and commits

- Status: `ready_for_review`
- Task base commit: `fd647c01da9d7cc968a28e0b7229e1993b92abe1`
- Work planning commit: `b5d6447cf42714c86b6986c5c25db1cf1f5eabf4`
- Implementation commit: `046c5e9`
- Branch: `codex/task055-logical-backup-readiness`

## Delivered behavior

- Added a non-authorizing logical-backup and isolated-restore-readiness runbook. It defines exact
  approval, credential, custom-format/schema-only dump, no-overwrite, checksum, retention, restore
  fidelity, stop and exposure-response boundaries.
- Added an offline Python tool with only `preflight`, `create` and `verify` actions. It accepts three
  absolute local artifact paths and can invoke only local `pg_restore --list` and `--version`; it has
  no connection, dump, restore, SQL or deletion interface.
- Path checks reject repository/traversal paths, symlink/reparse components, non-regular or empty
  archives, filename drift and existing planned/sidecar outputs. Sidecars use exclusive creation.
- Listing checks require PostgreSQL custom format, parse each TOC entry, reject unsupported/injected
  lines and reject application schemas other than `ntubtob`. Subprocess details, environment and the
  listing are not returned in errors.
- The fixed JSON manifest allows only generic purpose/version, UTC timestamp, basename, size,
  SHA-256, client major and three validation fields. Verification recomputes archive/listing/client,
  manifest and checksum contracts.
- Production migration preflight and evidence now require either adequate provider recovery or an
  explicitly accepted, retained and isolated-restore-tested logical archive boundary.

## Changed files

- `docs/operations/data/PORTAL_DATA_LOGICAL_BACKUP_RUNBOOK.md`
- `docs/operations/data/PORTAL_DATA_MIGRATION_EVIDENCE_TEMPLATE.md`
- `docs/operations/data/PORTAL_DATA_PRODUCTION_MIGRATION_RUNBOOK.md`
- `tests/portal_data/test_logical_backup.py`
- `tools/portal_data_logical_backup.py`
- `docs/coordination/reports/TASK-055-CODEX.md`
- `docs/coordination/HANDOFF.yaml`

## Verification performed

- `py -3.10 -m unittest tests.portal_data.test_logical_backup -v`: not run; the Windows launcher
  points at a missing Microsoft Store Python 3.10 executable and fails before Python starts.
- Equivalent available-runtime command using Visual Studio Python 3.9: 11/11 TASK-055 tests passed.
- Equivalent Python 3.9 `-m compileall -q tools tests/portal_data`: passed.
- Equivalent Python 3.9 `-m tools.portal_data_logical_backup --help`: passed and exposed only the
  three local artifact actions and paths.
- Full Python 3.9 `unittest discover -s tests/portal_data -v`: TASK-055 and dependency-free tests ran,
  but the suite failed four pre-existing-module imports because Alembic and SQLAlchemy are not
  installed in that runtime. No dependency installation was attempted.
- Black/isort: not run; the available runtime has neither module and Python 3.10 is unavailable.
  A line-length inspection found no lines over 88 characters after formatting adjustments.
- `git diff --check`: passed before the implementation commit.
- Docker/local PostgreSQL rehearsal: not run. Read-only Docker checks could not access the local
  config/engine pipe due permissions; no container, database or artifact was created.

Work or hosted CI must repeat the specified Python 3.10, Black and isort checks. The absence of a
local dump/list/restore rehearsal means restore fidelity remains unproven.

## Safety confirmation

- No `.env.yaml`, DSN, host, project ref, role, password, Secret or external Owner file was read.
- No remote/Supabase connection, production `pg_dump`, SQL, restore or migration occurred.
- No production data archive was created, inspected, copied or committed.
- No schema, role, grant, RLS, backup/PITR, cloud resource or deployment setting was changed.
- No push, PR, merge or deployment occurred.

## Assumptions, risk and Owner decisions

- The reviewed command remains a template; exact production client/server compatibility, direct
  reachability, encrypted storage, credential process and window require later Owner approval.
- `pg_restore --list` TOC behavior is covered by conspicuously fake output and mocks, not a real
  custom-format archive in this environment.
- Phase A and production backup remain blocked. Owner must later approve an exact production backup
  operation and, separately, an isolated non-production restore rehearsal before accepting logical
  recovery as the migration gate.
- Working tree was clean after the implementation commit; this report/handoff are the only completion
  changes pending their own descriptive commit.
