# Local Person and Event persistence

For the separately approved, production-shaped and pseudonymized read-only
preview workflow, see `LOCAL_PRODUCTION_SHAPED_PORTAL_PREVIEW.md`. The workflow
below remains the repository-local fake fixture rehearsal.

This environment exists only to rehearse the portal-data expand schema and
domain contracts. Its fake legacy fixture follows the ten-table, deidentified
TASK-049 catalog. It does not read `envs/**/.env.yaml`, does not connect to
Supabase, and is not imported by current Web Portal, LINE, webhook, or
scheduled-service request paths.

The local database gate accepts only PostgreSQL on `localhost`, `127.0.0.1`,
`::1`, or the Compose service `portal-postgres`, and only the database named
`ntubtob_portal_local`. Unknown, remote, and Supabase URLs fail closed.

## Install migration-only dependencies

These dependencies are deliberately separate from every deployed service's
runtime requirements.

Windows PowerShell:

```powershell
py -3.10 -m pip install -r requirements-migrations.txt
```

Unix-like:

```sh
python3 -m pip install -r requirements-migrations.txt
```

## Start the isolated PostgreSQL service

```sh
docker compose -f docker-compose.portal-data.yml config
docker compose -f docker-compose.portal-data.yml up -d portal-postgres
docker compose -f docker-compose.portal-data.yml ps
```

The default local port is `55432`. To avoid a collision, set
`PORTAL_DATA_POSTGRES_PORT` before `up`; use the same port in the local URL.
The port binds only to `127.0.0.1`; the Compose credentials and database name
are conspicuously local-only test values.

## Create the legacy fixture and migrate

Windows PowerShell:

```powershell
$env:PORTAL_DATA_DATABASE_URL = "postgresql+psycopg2://portal_local:local-only-password@127.0.0.1:55432/ntubtob_portal_local"
py -3.10 -m tools.setup_portal_data_legacy
py -3.10 -m alembic stamp 0001_legacy_baseline
py -3.10 -m alembic upgrade head
py -3.10 -m tools.seed_portal_data_fake
py -3.10 -m alembic current
```

Unix-like:

```sh
export PORTAL_DATA_DATABASE_URL='postgresql+psycopg2://portal_local:local-only-password@127.0.0.1:55432/ntubtob_portal_local'
python3 -m tools.setup_portal_data_legacy
python3 -m alembic stamp 0001_legacy_baseline
python3 -m alembic upgrade head
python3 -m tools.seed_portal_data_fake
python3 -m alembic current
```

`0001_legacy_baseline` is intentionally empty and represents the reviewed local
ten-table legacy fixture. A future production rollout must revalidate its exact
catalog before an explicitly approved baseline; these commands are not a
production runbook.

## Render and verify the review-only SQL artifact

This command performs no database connection and uses a fixed localhost-only
URL solely for Alembic offline rendering:

```powershell
py -3.10 -m tools.portal_data_migration_readiness render
py -3.10 -m tools.portal_data_migration_readiness verify
```

The adjacent SHA-256 sidecar and exact-source comparison make hand edits fail
closed. The SQL is explicitly marked `DO NOT RUN WITHOUT OWNER APPROVAL`.

Phase C adds a separate deterministic `0003 -> 0004` artifact and read-only
pre/post evidence:

```powershell
py -3.10 -m tools.portal_data_phase_c_migration render
py -3.10 -m tools.portal_data_phase_c_migration verify
py -3.10 -m tools.portal_data_phase_c_evidence
```

These commands render or verify repository files and may be executed only
against the named local database during rehearsal. The migration aborts
atomically if any attendance reply still cannot resolve a Person. Runtime
integration remains default-off behind `PORTAL_DATA_PHASE_C_ENABLED`; admin
mutations also require `WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED=true`.

## Run the shared contract suite

Windows PowerShell:

```powershell
$env:PORTAL_DATA_TEST_DATABASE_URL = $env:PORTAL_DATA_DATABASE_URL
py -3.10 -m unittest discover -s tests/portal_data -v
```

Unix-like:

```sh
export PORTAL_DATA_TEST_DATABASE_URL="$PORTAL_DATA_DATABASE_URL"
python3 -m unittest discover -s tests/portal_data -v
```

Without `PORTAL_DATA_TEST_DATABASE_URL`, the same command runs the in-memory
contract and safety tests and explicitly skips PostgreSQL cases.

With the isolated URL configured, the suite also injects a mid-migration error,
holds a real PostgreSQL lock until the artifact's bounded timeout fires, retries
after releasing the lock, and confirms fake legacy row counts are unchanged and
new tables remain empty.

## Rehearse downgrade and upgrade

This destructive downgrade is permitted only for this isolated local database.
Production rollback keeps the expand schema and rolls back the compatible
application instead.

```sh
python3 -m alembic downgrade 0001_legacy_baseline
python3 -m tools.setup_portal_data_legacy
python3 -m alembic upgrade head
```

On Windows, replace `python3` with `py -3.10`.

## Stop or remove only this local data

Stop the task-owned container while retaining its named volume:

```sh
docker compose -f docker-compose.portal-data.yml down
```

Delete only the Compose project's local named volume when a clean rehearsal is
intended:

```sh
docker compose -f docker-compose.portal-data.yml down -v
```

The command does not delete repository files. Do not substitute a workspace,
home directory, or broad filesystem path for this named-volume cleanup.
