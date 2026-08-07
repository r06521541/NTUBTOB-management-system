# TASK-051 Codex report

## Scope and commits

- Base commit: `00c98866ecdb7c217bf47a7f8bc2a0873603348f`
- Implementation commit: `f57a29c36210080d42b6953fdae98842905977d2`
- Branch: `codex/task051-production-migration-readiness`
- Scope: repository-only migration review artifact, fail-closed verifier, local PostgreSQL
  transaction/lock rehearsal, production runbook, sanitized evidence template and RLS decision
  package.

## Delivered behavior

- Alembic `0001 -> 0002 -> 0003` renders deterministically to one upgrade-only SQL artifact with
  explicit transaction boundaries, `lock_timeout = 5s`, `statement_timeout = 60s` and SHA-256.
- The verifier compares the committed artifact to current migration sources and exact single-head
  revision graph. It rejects destructive DDL, application DML, unexpected legacy table changes,
  remote/credential patterns, checksum drift and source drift.
- The renderer supplies a fixed localhost-only placeholder internally and never opens a database
  connection. It accepts no DSN or remote target argument.
- PostgreSQL regressions inject a mid-migration division-by-zero failure and a real lock timeout;
  both leave the baseline revision, legacy schema and data intact. A full retry succeeds after the
  lock is released.
- Another regression confirms all fake legacy aggregate row counts are unchanged and the new
  application tables remain empty after upgrade.
- The runbook separates Phase A schema expand, Phase B backfill and Phase C application rollout,
  with independent approval gates and no destructive production downgrade.

## Verification performed

All database commands used only the Compose database
`127.0.0.1:55432/ntubtob_portal_local` with conspicuous fake credentials/data.

- `docker compose -f docker-compose.portal-data.yml config`: passed; localhost binding confirmed.
- Offline artifact render and verify under Python 3.10.7: passed.
- Full downgrade to `0001`, exact fake fixture rebuild, baseline stamp, upgrade to head: passed.
- `py -3.10 -m alembic check`: `No new upgrade operations detected.`
- `py -3.10 -m unittest discover -s tests/portal_data -v`: 43/43 passed.
- Atomicity test: injected error rolled back new tables, `members.person_id` and version update.
- Lock test: 250ms test-only timeout failed without partial state; release and full retry passed.
- `py -3.10 -m compileall -q shared_lib/shared_module tools migrations tests/portal_data`:
  passed.
- Black and isort applied to the two new Python files.
- `git diff --check`: passed before implementation commit.
- Task-owned container stopped; named volume retained.

## Production decisions and unverified facts

- Backup/PITR readiness and restore authority are not verified.
- Production catalog freshness, version-table absence and safe baseline method are not reverified.
- Runtime database role, table owner, grants, RLS bypass behavior and Supabase API exposure remain
  unknown and are explicit stop conditions.
- The artifact does not enable RLS on new tables. The Owner must approve the RLS decision and any
  separately reviewed amendment before production schema execution.
- Production lock duration, network behavior and rollout compatibility are not proven by local
  tests.
- Phase B Member/identity backfill and Phase C application opt-in are not implemented or authorized.

## Safety confirmation

- No Supabase or production connection, query, stamp, DDL, backfill or RLS action occurred.
- No `.env.yaml`, Secret, credential or production row value was read or copied.
- No external API, LINE/Discord notification, cloud modification, deployment, push, PR or merge
  occurred.

## Handoff

Ready for Work to review the implementation commit, generated SQL/checksum, verifier mutation
coverage, local transaction/lock evidence and production stop gates. Acceptance must not be treated
as authorization for a production migration.
