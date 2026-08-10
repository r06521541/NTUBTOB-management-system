# Local fictional Portal demo

This workflow is for repeatable localhost UI and role QA using only repository-
owned fictional rows. It is separate from
`LOCAL_PRODUCTION_SHAPED_PORTAL_PREVIEW.md`: never seed while a cloud-derived
preview is loaded, and never enable fictional-demo mutation for that workflow.

## Prepare and seed

Use the repository Compose database, bundled Python, and the repository legacy
setup plus migration `0004_phase_c_identity_lifecycle` exactly as documented by
the production-shaped preview runbook. Do not connect to Supabase or another
host and do not provide a credential other than the fixed local Compose value.

```powershell
$TaskPython = 'C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PORTAL_DATA_DATABASE_URL = 'postgresql+psycopg2://portal_local:local-only-password@127.0.0.1:55432/ntubtob_portal_local'
& $TaskPython -m tools.seed_portal_ui_demo seed --confirm-fictional-demo
```

The tool validates the loopback URL, exact database name, revision, and either
the exact repository setup fixture or complete TASK-099 fixture before opening
its mutation transaction. Any arbitrary, mixed, partial, or cloud-derived state
is rejected without modification. Seed/reset output contains no row values.

## Start the fictional database-backed preview

```powershell
$env:WEB_PORTAL_ENV = 'development'
$env:WEB_PORTAL_LOCAL_PREVIEW_MODE = 'true'
$env:WEB_PORTAL_FICTIONAL_DEMO_MODE = 'true'
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

Open only `http://127.0.0.1:8080/local-preview/login`. The three chooser
identities are fictional Admin, Officer, and Basic. Only this exact mode and
complete fixture may exercise the audited `basic <-> officer` action. No other
Portal mutation is enabled and no external caller is used.

## Reset and cleanup

Stop the Portal before reset or cleanup.

```powershell
& $TaskPython -m tools.seed_portal_ui_demo reset --confirm-fictional-demo
& $TaskPython -m tools.seed_portal_ui_demo cleanup --confirm-fictional-demo
```

`reset` transactionally restores the deterministic fixture. `cleanup` accepts
only the complete TASK-099 fixture and transactionally removes its rows. For a
complete database removal, use the exact Compose `down -v` command from the
production-shaped preview runbook. Never substitute a wildcard, repository
root, home directory, remote DSN, or cloud-derived bundle path.
