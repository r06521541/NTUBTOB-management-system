# Local portal-data migrations

These revisions are a local rehearsal foundation, not authorization to stamp or
upgrade Supabase production. The local fixture now mirrors the ten-table,
deidentified TASK-049 catalog rather than the original two-table minimum.
Production must still revalidate its exact legacy schema, constraints and
migration state before any separately approved action.

`0001_legacy_baseline` is intentionally empty. Local rehearsal first creates the
minimal legacy fixture, stamps that baseline, then upgrades to the expand
revision. Emergency production rollback must prefer an application rollback
while retaining expand-only tables; the destructive downgrade exists for an
isolated local database only.

TASK-051 adds a deterministic, upgrade-only review artifact for the exact
`0001 -> 0002 -> 0003` chain. Render or verify it without a database connection:

```sh
python3 -m tools.portal_data_migration_readiness render
python3 -m tools.portal_data_migration_readiness verify
```

On Windows, replace `python3` with `py -3.10`. The verifier requires the exact
single revision chain and rejects destructive DDL, application DML, unexpected
legacy-table alterations, remote connection text and checksum/source drift.
The artifact is review material, not permission or a general production runner.
See `docs/operations/data/PORTAL_DATA_PRODUCTION_MIGRATION_RUNBOOK.md`.
