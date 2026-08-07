# TASK-057 Codex report

## Status and commits

- Status: `ready_for_review`
- Task base commit recorded by Work: `e2b75a8`
- Work planning commit / branch starting HEAD: `e27d296`
- Implementation commit: `df03a462c9daf54e3ba398748f0bf669b146abbd`
- Branch: `codex/task057-isolated-restore-rehearsal`

`e27d296` adds the TASK-057 specification on top of the recorded `e2b75a8` task base. Codex created
the implementation branch from that current planning commit and did not rewrite either commit.

## Delivered behavior

- Added `tools.portal_data_restore_rehearsal` with separate `preflight` and `execute` actions.
- `preflight` validates the adjacent repository-external archive/manifest/checksum path contract and
  never resolves or starts Docker.
- `execute` requires the exact `TASK-057-EPHEMERAL-LOCAL-RESTORE` acknowledgement and invokes the
  existing Docker archive verifier both before and after restore.
- The PostgreSQL server uses only the fixed local image ID with no pull, network, published port,
  persistent volume or Docker socket/repository/home mount. Its database, socket and temporary files
  use bounded tmpfs mounts; the archive parent is mounted read-only.
- The generated task-owned container uses a fixed prefix/label, read-only filesystem, non-root user,
  dropped capabilities and `no-new-privileges`. Success and failure paths remove it and independently
  confirm no matching container remains; cleanup ambiguity is terminal.
- Restore options are fixed to `--exit-on-error --single-transaction --no-owner --no-privileges`.
  There is no CLI passthrough for image, target, DSN, host, port, env-file, credential, SQL or restore
  options, and no `--clean`, `--create`, `--if-exists` or parallel job behavior.
- The fixed catalog query compares only deidentified TASK-049 contracts: schema/table set, all 53
  column type/nullability/default/identity/generated signatures, PK/FK relationships, constraint
  validation, primary indexes, absence of catalog-recorded custom checks/triggers/policies, RLS flags,
  identity sequences and completion of aggregate table scans. Output is restricted to 13 booleans;
  no values or exact row counts are returned.
- Updated the logical-backup runbook with commands, approval gates, isolation details, evidence limits
  and the still-blocked production archive rehearsal.

## Changed files

- `tools/portal_data_restore_rehearsal.py`
- `tests/portal_data/test_restore_rehearsal.py`
- `docs/operations/data/PORTAL_DATA_LOGICAL_BACKUP_RUNBOOK.md`
- `docs/coordination/reports/TASK-057-CODEX.md`
- `docs/coordination/HANDOFF.yaml`

## Verification performed

- Visual Studio Python 3.9 focused TASK-057 suite: 10/10 passed.
- Bundled Python 3.12 combined restore/logical-backup suites: 29/29 passed.
- Python 3.9 `py_compile` for the new tool and tests: passed.
- `git diff --check`: passed before the implementation commit.
- Final real local fake-data Docker rehearsal: passed. It created a conspicuously fake custom archive
  in a system temporary directory, created its fake sidecars, verified the archive, restored into the
  no-network/no-port tmpfs database, passed all 13 catalog categories, re-verified the archive and
  confirmed no TASK-057 container remained. The generator container and temporary directory were
  removed.
- An earlier fake-fixture attempt failed before wrapper execution because the host PowerShell did not
  accept one directory-creation parameter and Python 3.9 could not import an optional SQLAlchemy
  dependency. Its task-owned generator container was independently confirmed absent. The fixture
  harness was corrected without changing security boundaries, and the two later fake rehearsals
  passed.

## Environment limitations

- The registered `py -3.10` executable still points to an unavailable Microsoft Store path, so local
  Python 3.10 could not run. Python 3.10 evidence remains required from hosted CI after an authorized
  push/PR.
- Visual Studio Python 3.9 has neither Black nor isort installed. The bundled Python 3.12 Black entry
  point did not return output and was terminated; no dependency installation was attempted. Work/CI
  must run the specified formatter checks.

## Safety confirmation

- No production archive, manifest, checksum or credential env-file was opened, mounted or inspected.
- No Supabase/remote database connection, production SQL, schema change, migration, notification,
  deployment, push, PR or merge occurred.
- Docker use was limited to the fixed already-local image and conspicuously fake data. Every container
  used `--network none`, no published port and no persistent volume. Task-owned resources were removed.
- No archive listing, row value, exact count, identity, credential or subprocess output was committed.

## Remaining risk and next gate

- Work must inspect the actual diff/commit, rerun focused tests and formatter checks, and obtain hosted
  Python 3.10 CI evidence after a separately authorized PR package.
- The fake-data rehearsal proves local wrapper mechanics only. It does not prove application rollback,
  Supabase grants/API exposure, provider disaster recovery or production data fidelity.
- Using the retained production artifact set remains prohibited until this implementation is reviewed,
  merged and Owner separately approves the exact merged commit, three artifact basenames and cleanup
  boundary. No production dump retry is needed or authorized.
