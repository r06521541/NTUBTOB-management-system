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
- evidence form: `PORTAL_DATA_MIGRATION_EVIDENCE_TEMPLATE.md`

## Phase separation

1. **Phase A — schema expand:** baseline, one transaction, no rows written except Alembic version.
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
- backup/PITR is active, retention covers the window, restoration authority and procedure are known;
- migration role can create/alter required objects, and its relation to table ownership is understood;
- runtime database role, grants, RLS bypass behavior and Supabase API exposure are known;
- Owner approved the RLS choice, including any separately reviewed amendment to the artifact;
- no concurrent deployment, backfill, schema task or long-running transaction targets these tables;
- maintenance window allows immediate stop on the first timeout or catalog mismatch.

Do not infer backup readiness from a plan name or dashboard badge. The authorized operator must
verify it in the provider control plane without copying sensitive metadata into this repository.

## Baseline gate

Because production had no Alembic version table during TASK-049, baseline is a metadata assertion,
not a migration. The operator must independently prove that production legacy objects match the
sanitized catalog before recording `0001_legacy_baseline`. If the version table now exists, contains
another revision, or catalog drift appears, stop; do not overwrite, purge or re-stamp it.

Baseline recording and schema execution must use the Owner-approved transaction plan. Do not run
the local setup tool, local fixture, downgrade command or autogenerate against production.

## Phase A execution contract

- Execute only the reviewed SQL bytes whose SHA-256 matches the approved sidecar.
- Use its single explicit transaction with transaction-local `lock_timeout = 5s` and
  `statement_timeout = 60s`.
- Do not edit around a timeout, retry individual statements or add ad-hoc RLS/grant SQL.
- The only allowed row mutation is Alembic version bookkeeping.
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
- RLS/grant state matches the separately approved decision;
- current applications remain on legacy paths and no notification/external API was triggered.

Record only sanitized yes/no and checksum evidence using the template.

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

TASK-051 proves only the following against isolated localhost PostgreSQL:

- deterministic source-to-artifact rendering and checksum verification;
- fail-closed rejection of destructive DDL, DML, legacy ownership drift and remote/credential text;
- atomic rollback on an injected mid-migration failure;
- bounded lock failure with no partial schema, followed by a successful full retry;
- unchanged fake legacy row counts and zero new application rows.

It does not prove production backup, lock duration, RLS policies, roles, API exposure or network
behavior. Those remain mandatory preflight facts.
