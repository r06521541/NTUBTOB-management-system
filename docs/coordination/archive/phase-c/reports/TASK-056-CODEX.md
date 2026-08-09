# TASK-056 Codex report

## Status and commits

- Status: `ready_for_review`
- Task base commit: `4d4ee40a8561ad7cfc0c8a3d86aea0c5fe2bc554`
- Work planning commit: `dd4c104d191e94b07c1d3bb5f42448612261ca3c`
- Implementation commit: `ea241f7`
- Branch: `codex/task056-production-backup-authorization`

### TOC identifier compatibility correction

- Correction base: `0e8138e09688eff8ae87ba8881f9ae5cbbb9a1d6`
- Work planning commit: `80f35d7d8c0f7bbda091971407f29d172e1d81c2`
- Correction commit: `50902dd`
- Correction branch: `codex/task056-toc-identifier-compatibility`
- Work reported that the approved session-pooler dump produced one retained 56,903-byte custom
  archive, but verifier evidence creation failed closed before sidecar creation. Codex did not access
  that archive, its destination or the credential env-file.
- The failure was reproduced only with a conspicuously fake TOC line containing the repository-known
  legitimate identifier `line_notify_tokens`. The previous unbounded `token` alternative matched the
  identifier substring.
- `password`, `secret` and `token` now require ASCII identifier boundaries. Standalone terms and
  hyphen-delimited values remain rejected, while `line_notify_tokens` is accepted as one identifier.
- The fake TOC regression covers all ten legacy table names recorded in the committed, sanitized
  TASK-049 catalog, preventing another known identifier-substring collision from escaping review.
- URL/DSN, SQL injection, foreign-schema, arbitrary-TOC and standard comment-metadata defenses are
  unchanged.

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

Correction verification:

- Available Visual Studio Python 3.9 focused suite: 19/19 passed, including the new legitimate
  identifier regression across all ten TASK-049 legacy tables and standalone
  `token`/`secret`/`password`/`token-value` mutations.
- Available Python 3.9 compile check: passed.
- `git diff --check`: passed before the correction commit.
- Python 3.10, Black and isort commands could not start because the configured Microsoft Store
  Python executable remains unavailable; Work/hosted CI must repeat them.

## Safety confirmation

- No env-file, `.env.yaml`, DSN, credential, Secret, host, project ref, role or external Owner file was
  opened or read.
- No Docker image was pulled and no container was started.
- No Supabase/remote connection, `pg_dump`, restore, SQL, migration or production archive handling
  occurred.
- No production data, schema, RLS/grant/role, cloud resource or deployment setting was touched.
- No push, PR, merge or deployment occurred.
- During the correction, Codex did not read or inspect the retained production archive or env-file,
  start Docker, connect remotely, execute dump/restore/SQL/migration or create sidecars.

## Remaining risk and next gate

- Work must independently inspect commit `ea241f7`, rerun Python 3.10/Black/isort checks and obtain
  hosted CI evidence after separate PR authorization.
- Work may later perform an isolated fake-archive Docker backend rehearsal only under its approved
  scope; this Codex task does not prove Docker Desktop path syntax against the intended destination.
- Production dump remains blocked. This prerequisite does not authorize env-file access, Supabase,
  archive creation/inspection, restore, migration or any production operation.
- Re-verifying the retained archive remains blocked until this correction is reviewed, merged and
  separately approved by Owner; the production dump must not be repeated.
