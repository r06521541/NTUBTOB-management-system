# Portal Data Phase C production migration readiness

> **STOP: this package does not authorize production access or migration.** It prepares the exact
> repository artifacts for a later Owner-operated window. Runtime flags and identity maintenance
> remain off throughout this procedure.

## Fixed artifacts

- Inventory: `docs/operations/sql/TASK-071-phase-c-production-inventory.sql`
- Migration: `docs/operations/sql/portal-data-0003-to-0004.sql`
- Post-check: `docs/operations/sql/TASK-071-phase-c-production-postcheck.sql`
- Each SQL file has an adjacent SHA-256 sidecar. Do not edit SQL in the database console.
- Offline verification:

```powershell
python -m tools.portal_data_phase_c_migration verify
python -m tools.portal_data_phase_c_readiness verify
```

The inventory and post-check return only the fixed sanitized CSV columns
`section,metric,status,boolean_value,integer_value,text_value`. Runtime flag state is explicitly
reported as `not_checked_by_database`; verify it separately without recording values or secrets.

## Approval and freshness gates

Before opening a migration window, record the exact merged 40-character commit and all three
approved checksums. Confirm provider backup/PITR readiness in the provider control plane. This
repository does not prove backup availability, production role behavior, current locks or API
exposure.

The inventory is fresh for at most 30 minutes. During that interval freeze deployments, identity
approval/remap/unlink, Member/Person matching, attendance maintenance and manual SQL touching the
covered tables. If the interval expires or any freeze is broken, discard the CSV and start again.
Do not commit either CSV.

Required sequence:

1. Owner runs the exact checksummed read-only inventory and exports its sole result as CSV.
2. Work validates it offline with
   `python -m tools.portal_data_phase_c_readiness validate --kind inventory <inventory.csv>`.
3. Work confirms revision `0003`, zero Phase C collisions, Phase A/B/RLS/audit invariants, resolved
   attendance ownership and acceptable session privilege risk. A superuser or BYPASSRLS result is a
   stop gate requiring a new explicit risk decision, even though it is reported as `risk`.
4. Owner issues a new approval naming the exact commit, migration checksum, target, operator and
   window. Earlier repository or Phase B approval is insufficient.
5. Owner executes the exact migration once, as a single transaction. No statement may be copied,
   skipped, retried individually or augmented with cleanup, grants, roles or policies.
6. Owner immediately runs the exact post-check and exports its sole result as CSV.
7. Work validates and compares the pair:

```powershell
python -m tools.portal_data_phase_c_readiness validate --kind postcheck <postcheck.csv>
python -m tools.portal_data_phase_c_readiness compare <inventory.csv> <postcheck.csv>
```

Only `pass` permits closing the schema migration. Application deployment and flag enablement are
separate tasks requiring separate approval. Keep `PORTAL_DATA_PHASE_C_ENABLED` and identity
maintenance disabled.

## Stop and recovery boundary

- **Known SQL error or timeout, rollback confirmed:** stop, preserve sanitized evidence, resolve the
  lock/cause, rerun a fresh inventory, obtain a new exact approval and retry the whole transaction
  once. Never retry from the failed statement.
- **Connection loss or unknown transaction outcome:** this is an ambiguous commit. Do not rerun the
  migration. Use a newly approved read-only session to establish the single Alembic revision and
  execute the matching inventory/post-check evidence before any decision.
- **Revision still exactly `0003` and no Phase C object survives:** comparison may classify
  `safe_retry_after_confirmed_rollback`; the 30-minute/freeze/approval sequence still restarts.
- **Revision exactly `0004` and post-check passes:** retain the expand schema, keep application
  features off, and close only the migration step.
- **Revision `0004` but post-check or aggregate comparison fails:** classify semantic drift. Freeze
  rollout and identity/attendance writes, preserve evidence, and create a forward-recovery task.
  Do not downgrade, drop, truncate, delete audit rows, disable triggers or restore over production.
- **Unexpected revision, multiple revision rows, partial catalog or unverifiable outcome:** classify
  ambiguous commit and escalate. Do not stamp Alembic or use `IF NOT EXISTS` to force progress.

The 0004 migration is expand-only for legacy services. Application rollback therefore means keeping
the legacy feature flags off; it is not schema rollback.

## Local PostgreSQL 16 rehearsal boundary

Tests use only the repository localhost database fixture and fake values. They cover deterministic
render/checksum/graph validation, encoding and mutation rejection, clean 0003-to-0004 execution,
attendance backfill invariants, atomic unresolved-row rollback, bounded lock failure and full retry,
strict evidence validation, drift negatives and inventory/post-check comparison. Local success does
not prove production locks, data shape, ownership, backup, transaction duration or runtime flags.
