# Portal Data production migration runbook

> **STOP: this document does not authorize production access or schema changes.** Use it only after
> the Owner approves the exact commit, SQL checksum, target environment, maintenance window,
> baseline method, RLS decision and recovery boundary. Never paste credentials into commands,
> terminals, logs or repository evidence.

## Scope

Phase A adds the Person/access/qualification/Event schema and nullable `members.person_id`, then
aligns `activities.game_id` to legacy bigint IDs. It deliberately performs no Member backfill, no
identity mapping, no application rollout and no destructive downgrade.

Reviewed inputs:

- SQL: `docs/operations/sql/portal-data-0001-to-0003.sql`
- checksum: adjacent `.sha256` file
- sanitized production catalog: `TASK-049-SUPABASE-CATALOG-SANITIZED.md`
- RLS decisions: `PORTAL_DATA_RLS_DECISION_PACKAGE.md`
- logical backup controls: `PORTAL_DATA_LOGICAL_BACKUP_RUNBOOK.md`
- evidence form: `PORTAL_DATA_MIGRATION_EVIDENCE_TEMPLATE.md`
- execution-time pre-check: `docs/operations/sql/TASK-062-phase-a-precheck.sql`
- execution-time post-check: `docs/operations/sql/TASK-062-phase-a-postcheck.sql`

Both checks have adjacent SHA-256 sidecars. Verify the fixed repository artifacts offline before the
window with `python -m tools.portal_data_phase_a_evidence verify-repository`. Never edit either SQL
file in the SQL Editor.

## Phase separation

1. **Phase A — schema expand:** create and record the baseline marker, upgrade through `0003`, and
   enable zero-policy RLS in one transaction; no rows are written except Alembic version bookkeeping.
2. **Phase B — identity/Member backfill:** separate design, idempotency evidence and approval.
3. **Phase C — application opt-in:** deploy compatible readers/writers only after Phase B review.

Approval of one phase never authorizes the next.

## Required preflight

Stop unless every item is confirmed immediately before the window:

- exact 40-character source commit and reviewed SHA-256 match;
- the verifier succeeds and the generated artifact exactly matches migration sources;
- TASK-049 catalog fingerprint still matches columns, types, nullability, defaults, identity,
  PK/FK and RLS flags;
- `ntubtob.alembic_version` is absent and there is no other migration owner/history;
- either provider backup/PITR covers the full window, or a separately approved `ntubtob` logical
  archive has passed checksum, sanitized-manifest, retained-copy and isolated restore-fidelity gates;
- the exact recovery artifact remains available through Phase A verification and Owner confirmation;
- migration role can create/alter required objects, and its relation to table ownership is understood;
- runtime database role, grants, RLS bypass behavior and Supabase API exposure are known;
- Owner approved the RLS choice, including any separately reviewed amendment to the artifact;
- no concurrent deployment, backfill, schema task or long-running transaction targets these tables;
- maintenance window allows immediate stop on the first timeout or catalog mismatch.

Do not infer backup readiness from a plan name or dashboard badge. The authorized operator must
verify it in the provider control plane without copying sensitive metadata into this repository.

## Baseline gate

Because production had no Alembic version table during TASK-059, baseline is a reviewed metadata
assertion recorded by the exact artifact. The operator must independently prove that production
legacy objects match the sanitized catalog immediately before execution. The artifact then creates
the canonical version table, inserts exactly `0001_legacy_baseline`, applies `0002` and `0003`, and
updates the marker twice in that same transaction. If the version table now exists, any portal-data
object exists, or catalog drift appears, stop; do not overwrite, purge, re-stamp, add `IF NOT EXISTS`,
or retry individual statements.

Baseline recording and schema execution must use the Owner-approved transaction plan. Do not run
the local setup tool, local fixture, downgrade command or autogenerate against production.

## Phase A execution contract

Immediately before migration, execute the exact TASK-062 pre-check in a new SQL Editor query and
export its only result table as CSV. Stop on any SQL Editor warning/error, extra result set or strict
validator rejection. Keep the CSV outside the repository; do not modify the query to work around a
failure.

```powershell
python -m tools.portal_data_phase_a_evidence validate-pre <absolute-pre.csv>
```

- Execute only the reviewed SQL bytes whose SHA-256 matches the approved sidecar.
- Use its single explicit transaction with transaction-local `lock_timeout = 5s` and
  `statement_timeout = 60s`.
- Do not edit around a timeout, retry individual statements or add ad-hoc RLS/grant SQL.
- The only allowed row mutation is Alembic version bookkeeping.
- Exactly the 13 new portal-data tables enable RLS without `FORCE`; the artifact creates zero
  policies and performs no `GRANT` or `REVOKE`.
- On a lock timeout, statement timeout, constraint/catalog error or connection loss, treat the run
  as failed until rollback is confirmed. Release competing work before one full retry.
- Never run the destructive Alembic downgrade in production.

## Success checks

All checks are required before declaring Phase A complete:

- transaction committed once and revision is exactly `0003_legacy_bigint_activity_game`;
- expected tables, constraints, indexes, append-only function and triggers exist;
- `members.person_id` is nullable, unique/FK protected and contains no backfill values;
- all ten legacy table aggregate row counts are unchanged;
- new portal-data application tables contain zero rows;
- all 13 new tables have RLS enabled, not forced, with zero policies; grants are unchanged;
- current applications remain on legacy paths and no notification/external API was triggered.

Record only sanitized yes/no and checksum evidence using the template.

Execute the exact TASK-062 post-check in a new SQL Editor query and export its only result table as
CSV. Validate the pair offline with:

```powershell
python -m tools.portal_data_phase_a_evidence validate <absolute-pre.csv> <absolute-post.csv>
```

The validator requires the exact six-column contract and every allowlisted metric. The pre-check
repeats the TASK-061 legacy table/column/PK-FK fingerprints and the approved generic schema owner,
usage/create, relation ownership and privilege counts. The post-check requires the exact approved
legacy fingerprint transition (only nullable `members.person_id` plus its reviewed FK changes) and
the same legacy access counts. It fails closed on missing, duplicate or unknown metrics; catalog
fingerprint drift; non-empty Phase A tables; `members.person_id` backfill; RLS/policy drift; PUBLIC
or non-owner portal grants; non-owner table default ACLs; or any legacy aggregate/access change.
Never commit these ephemeral CSV files. A successful transaction without a passing post-check is not
a completed migration.

## Stop and recovery

Before commit, PostgreSQL transactional DDL should roll back schema and version changes together.
Confirm the version remains at the pre-run state and no new object or `members.person_id` survives.
Do not assume rollback after an ambiguous connection loss; verify through an approved read-only
session before retrying.

After commit, retain the expand schema and roll back/hold application rollout. Do not downgrade or
drop tables: an expand-only schema is compatible with legacy services, while destructive cleanup
can lose future or partially written data. If post-checks fail, freeze Phase B/C, preserve evidence,
and request a new recovery decision from the Owner.

## Local rehearsal evidence

TASK-060 proves the following against isolated localhost PostgreSQL with conspicuously fake data:

- deterministic source-to-artifact rendering and checksum verification;
- fail-closed rejection of destructive DDL, DML, unexpected legacy-table creation/alteration, and
  remote/credential text;
- creation of the absent canonical marker, its `0001` insert, and upgrades through `0003` in one
  transaction;
- exactly 13 RLS-enabled, not-forced, zero-policy tables;
- atomic rollback on an injected mid-migration failure, including marker creation;
- bounded lock failure with no partial schema, followed by a successful full retry;
- fail-closed rejection of a pre-existing marker or portal-data object;
- unchanged fake legacy row counts and zero new application rows.

It does not prove current production fingerprints, lock duration, roles, API exposure or network
behavior. TASK-059 must be rerun after the TASK-060 merge and before any execution approval.
