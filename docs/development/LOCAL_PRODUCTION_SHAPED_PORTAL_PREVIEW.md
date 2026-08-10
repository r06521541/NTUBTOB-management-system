# Local production-shaped Portal preview

This runbook prepares a localhost-only, read-only Portal preview from an
Owner-operated export. It does not authorize connecting to Supabase, handling a
credential, exporting rows, or changing production. The source and derived
bundles and pseudonymization seed are private artifacts: keep all three outside
the repository, encrypted at rest, and out of terminal transcripts, reports,
screenshots, and Git.

The repository side of the boundary consists of:

- the six fixed, read-only queries in `tools/portal_preview_export/`;
- `tools.portal_data_local_preview`, which seals, validates, pseudonymizes, and
  imports the bundle without a source-database caller;
- the existing `ntubtob_portal_local` Compose database and migration chain;
- the double-gated `/local-preview/login` identity chooser and production Portal
  routes/templates.

## 1. Review and separately approve the export

Before any source connection, the Owner must review and approve the exact commit,
all six SQL files, source environment, operator, private output directory, and
retention/cleanup plan. Every query begins a read-only transaction, selects only
the fixed allowlist, and excludes raw provider subjects, administrative notes,
audit reasons/JSON, provider user IDs, credentials, tokens, and secrets.

Codex must not run this step or receive the source DSN/credential. After approval,
the Owner runs each file with an independently secured `psql` connection and
options equivalent to `-X -qAt --set ON_ERROR_STOP=1`. Direct each file's query
output to the corresponding private JSONL filename:

```text
people.jsonl
members.jsonl
games.jsonl
auth_identities.jsonl
person_qualifications.jsonl
game_attendance_replies.jsonl
```

Do not paste commands containing a DSN into a report or shared transcript. A
nonzero `psql` exit, extra output, unknown field, or partial file invalidates the
bundle; remove that exact failed private bundle and start again.

## 2. Seal and pseudonymize outside the repository

Use the bundled runtime required by the task:

```powershell
$TaskPython = 'C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$PrivateRawBundle = 'C:\replace-with-private-location\portal-preview-raw'
$PrivateDerivedBundle = 'C:\replace-with-private-location\portal-preview-derived'
$PrivateSeedFile = 'C:\replace-with-private-location\portal-preview.seed'

& $TaskPython -m tools.portal_data_local_preview seal-raw $PrivateRawBundle
& $TaskPython -m tools.portal_data_local_preview validate $PrivateRawBundle --kind raw
& $TaskPython -m tools.portal_data_local_preview pseudonymize $PrivateRawBundle $PrivateDerivedBundle --seed-file $PrivateSeedFile --anchor-date 2026-08-20
& $TaskPython -m tools.portal_data_local_preview validate $PrivateDerivedBundle --kind derived
```

Create the seed with an approved local cryptographic random generator; it must
contain at least 32 bytes and must never be committed or logged. Choose an
explicit preview anchor date. The tool shifts all exported timestamps by one
common offset, preserving ordering and intervals while placing the first game on
that date. Reusing the same raw bundle, seed, and anchor produces identical IDs,
names, relationships, and checksums.

Validation fails closed on unknown files/tables/fields, malformed types, row
limits, duplicate IDs, missing foreign keys, revision drift, row-count drift, or
checksum drift. Error messages never include row values.

## 3. Prepare only the isolated PostgreSQL database

```powershell
docker compose -f docker-compose.portal-data.yml up -d portal-postgres

$env:PORTAL_DATA_DATABASE_URL = 'postgresql+psycopg2://portal_local:local-only-password@127.0.0.1:55432/ntubtob_portal_local'
& $TaskPython -m tools.setup_portal_data_legacy
& $TaskPython -m alembic stamp 0001_legacy_baseline
& $TaskPython -m alembic upgrade 0004_phase_c_identity_lifecycle
& $TaskPython -m tools.portal_data_local_preview import $PrivateDerivedBundle
```

The importer reuses `require_local_database_url`; remote/Supabase hosts and any
database name other than `ntubtob_portal_local` are rejected before engine
creation. It also requires revision `0004_phase_c_identity_lifecycle`, an empty
target, the exact derived manifest, checksums, types, limits, and foreign keys.
All six tables are inserted in one transaction; an error rolls everything back,
and a corrected bundle can be retried against the still-empty target. In that
same transaction, the importer replaces only the known `setup_portal_data_legacy`
fake attendance lookup IDs with the fixed 1–5 local preview semantics; any other
lookup set fails closed.

## 4. Start the loopback-only, read-only Portal

```powershell
$env:WEB_PORTAL_ENV = 'development'
$env:WEB_PORTAL_LOCAL_PREVIEW_MODE = 'true'
$env:WEB_PORTAL_DEMO_MODE = 'false'
$env:WEB_PORTAL_BIND_HOST = '127.0.0.1'
$env:PORTAL_DATA_PHASE_C_ENABLED = 'true'
$env:DSN_HOSTNAME = '127.0.0.1'
$env:DSN_PORT = '55432'
$env:DSN_DATABASE = 'ntubtob_portal_local'
$env:DSN_UID = 'portal_local'
$env:DSN_PASSWORD = 'local-only-password'

& $TaskPython apps/web_portal/app.py
```

Open only `http://127.0.0.1:8080/local-preview/login`. The chooser displays safe
pseudonymous Person labels and persisted preview access levels without exposing
provider subjects. Production Portal routes continue through their existing
callers/repositories and templates. Any non-loopback Host, production mode,
inexact preview flag, mismatched database settings, LINE login/callback, or
Portal POST other than preview login/logout fails closed. No LINE/Discord helper
is instantiated, and no Portal data mutation is accepted in preview mode.

## 5. Verification and exact cleanup

Run offline checks before use. PostgreSQL integration should run against both the
PostgreSQL 15 and 16 CI service images on the final PR:

```powershell
& $TaskPython -m unittest tests.portal_data.test_local_preview_bundle -v
& $TaskPython -m unittest discover -s apps/web_portal/tests -v
```

Stop the Portal process, then remove only the exact local Compose database:

```powershell
docker compose -f docker-compose.portal-data.yml down -v
```

Finally, delete only the three exact private paths selected above according to
the approved retention plan. Do not substitute a workspace root, home directory,
wildcard, or unresolved environment variable. The Git ignore entries are a final
defense, not permission to place private artifacts in the repository.
