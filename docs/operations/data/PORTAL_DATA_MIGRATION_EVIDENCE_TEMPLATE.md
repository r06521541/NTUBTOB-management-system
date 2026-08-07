# Portal Data production migration evidence template

> 此模板只記錄去識別化證據，不是執行授權。禁止填入 database host、帳號、角色名稱、
> DSN、Secret、資料列內容、精確資料量或其他可識別 production 的資訊。

## 1. Approval and source

- Owner approval reference:
- Approved source commit (40 characters):
- Reviewed SQL artifact path:
- Reviewed SQL SHA-256:
- Expected revision range: `0001_legacy_baseline -> 0003_legacy_bigint_activity_game`
- Executor and reviewer roles (generic labels only):
- Approved maintenance window (timezone and duration only):

## 2. Preflight result

- Backup/PITR readiness confirmed by Owner: `yes / no`
- Restore procedure and authority confirmed: `yes / no`
- Catalog fingerprint matches TASK-049 sanitized catalog: `yes / no`
- `ntubtob.alembic_version` absent before baseline: `yes / no`
- Legacy object ownership and migration permissions confirmed: `yes / no`
- Runtime database role and table-owner relationship reviewed: `yes / no`
- Supabase API exposure for `ntubtob` reviewed: `yes / no`
- RLS decision recorded and approved: `yes / no`
- Conflicting application/deployment change frozen: `yes / no`

Stop if any answer is `no` or unknown.

## 3. Execution evidence

- Start and finish timestamps:
- Baseline method approved:
- Pre-execution revision state (revision only):
- Applied SQL checksum matches reviewed checksum: `yes / no`
- Transaction-local `lock_timeout`: `5s`
- Transaction-local `statement_timeout`: `60s`
- Result: `committed / rolled back / stopped`
- Error category, if any (sanitized; no SQL values or connection details):

## 4. Post-check result

- Revision is exactly `0003_legacy_bigint_activity_game`: `yes / no`
- Expected new tables, constraints, indexes, function and triggers exist: `yes / no`
- `members.person_id` exists, nullable and empty: `yes / no`
- Legacy table aggregate counts unchanged: `yes / no`
- New tables contain zero application rows: `yes / no`
- Runtime services were not opted into the new schema: `yes / no`
- RLS state matches the approved decision: `yes / no`
- Secret, IAM, Scheduler and notification state unchanged: `yes / no`

## 5. Outcome and next gate

- Outcome:
- Recovery action, if any:
- Sanitized evidence reviewed by:
- Phase B backfill authorized: `no` unless separately approved
- Phase C application rollout authorized: `no` unless separately approved
