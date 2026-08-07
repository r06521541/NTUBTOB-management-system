# TASK-056 Codex report

## Status and commits

- Status: `ready_for_review`
- Task base commit: `4d4ee40a8561ad7cfc0c8a3d86aea0c5fe2bc554`
- Work planning commit: `dd4c104d191e94b07c1d3bb5f42448612261ca3c`
- Implementation commit: `ea241f7`
- Branch: `codex/task056-production-backup-authorization`

## Delivered behavior

- Added an explicit `--backend docker` inspection path while preserving `host` as the CLI default.
- The Docker command uses only fixed image ID
  `sha256:89ec47deeeddac28eb60b5672a456c54213ff4528f8752fda7f7c2a0e4ead36a`
  and adds `--pull never`, `--network none`, `--read-only`, `--cap-drop ALL` and
  `--security-opt no-new-privileges`.
- Only the validated archive parent is bind-mounted at `/backup` with `readonly`; repository paths,
  direct home-directory mounts, symlink/reparse paths, invalid archives and comma-delimited mount
  sources fail closed.
- The runner accepts exactly `pg_restore --list` for its configured archive or
  `pg_restore --version`. It rejects alternate archives, arbitrary backend values and added Docker/
  pg_restore/database options before subprocess execution.
- Docker is called with an argument list, `shell=False`, bounded timeout and captured output. Only
  host process-discovery variables are passed to the Docker client; no container environment,
  env-file, credential, database/network parameter, repository/home/socket mount or output detail is
  passed or logged.
- `preflight`, including `preflight --backend docker`, remains path-only and never resolves or starts
  Docker. Host create/verify behavior remains the default.
- Updated the logical-backup runbook with the fixed Docker inspection contract and safe CLI usage.

## Changed files

- `tools/portal_data_logical_backup.py`
- `tests/portal_data/test_logical_backup.py`
- `docs/operations/data/PORTAL_DATA_LOGICAL_BACKUP_RUNBOOK.md`
- `docs/coordination/reports/TASK-056-CODEX.md`
- `docs/coordination/HANDOFF.yaml`

## Verification performed

- Available Visual Studio Python 3.9 equivalent unit command: 18/18 tests passed. The five Docker
  tests mock all subprocesses and verify exact argv/security flags, fixed image, read-only mount,
  list/version commands, host default, no-Docker preflight, rejection and output-hiding paths.
- Available Python 3.9 `-m compileall -q tools tests/portal_data`: passed.
- `git diff --check`: passed before the implementation commit.
- A line-length inspection reported no TASK-056 Python lines over 88 characters.
- Specified Python 3.10 unit, compile, Black and isort commands could not start because the Windows
  launcher points to a missing Microsoft Store Python 3.10 executable. No package/runtime install was
  attempted. Hosted Python 3.10 CI therefore remains required after a separately authorized push/PR.
- No real Docker command was executed; behavior is offline/mock verified only.

## Safety confirmation

- No env-file, `.env.yaml`, DSN, credential, Secret, host, project ref, role or external Owner file was
  opened or read.
- No Docker image was pulled and no container was started.
- No Supabase/remote connection, `pg_dump`, restore, SQL, migration or production archive handling
  occurred.
- No production data, schema, RLS/grant/role, cloud resource or deployment setting was touched.
- No push, PR, merge or deployment occurred.

## Remaining risk and next gate

- Work must independently inspect commit `ea241f7`, rerun Python 3.10/Black/isort checks and obtain
  hosted CI evidence after separate PR authorization.
- Work may later perform an isolated fake-archive Docker backend rehearsal only under its approved
  scope; this Codex task does not prove Docker Desktop path syntax against the intended destination.
- Production dump remains blocked. This prerequisite does not authorize env-file access, Supabase,
  archive creation/inspection, restore, migration or any production operation.
