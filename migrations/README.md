# Local portal-data migrations

These revisions are a local rehearsal foundation, not authorization to stamp or
upgrade Supabase production. Production must first inventory its exact legacy
schema, constraints, rows, and current migration state.

`0001_legacy_baseline` is intentionally empty. Local rehearsal first creates the
minimal legacy fixture, stamps that baseline, then upgrades to the expand
revision. Emergency production rollback must prefer an application rollback
while retaining expand-only tables; the destructive downgrade exists for an
isolated local database only.
