# TASK-097 Work Review

status: changes_requested
reviewer: work
reviewed_at: 2026-08-10T09:23:30+08:00
branch: codex/phase-d-local-cloud-data-preview
implementation_commit: 3ccd2f49e900b1b2ca07fe478a160cdad0566a26

## Review result

Changes requested. The security gates, private-bundle validation, pseudonymization and isolated PostgreSQL evidence are
otherwise well scoped, but the documented Owner workflow cannot currently reach a successful import.

## Blocking finding

`LOCAL_PRODUCTION_SHAPED_PORTAL_PREVIEW.md` instructs the Owner to run `tools.setup_portal_data_legacy`, stamp the legacy
baseline, upgrade to `0004_phase_c_identity_lifecycle`, and then invoke the importer. The setup command inserts fictional
Member, Game and attendance rows; the migration chain also creates their Phase C projections. The importer then rejects
every non-empty target table with `local preview target tables must be empty`.

The PostgreSQL integration suite does not reproduce that workflow because `LocalPreviewPostgresIntegrationTest.setUp`
truncates all six target tables before every import. As a result, PG15/16 passed a pre-cleared state that the runbook never
creates, while an Owner following the documented commands will fail.

## Required correction

- Make the importer/runbook succeed from the exact freshly prepared local fixture at revision
  `0004_phase_c_identity_lifecycle`, without an undocumented manual SQL step.
- Preserve fail-closed behavior for arbitrary non-empty databases. Prefer recognizing the exact repository-owned local
  fixture and replacing it together with the derived bundle in the same transaction; do not add a broad unguarded truncate.
- Update PostgreSQL integration to begin from the actual setup/migration state rather than calling the test-only `_clear`
  before the successful import. Keep late-failure rollback and corrected retry evidence on PostgreSQL 15 and 16.
- Correct the runbook and Codex report to match the verified workflow.

## Work targeted verification

- `LocalPreviewBundleTest`: 5 passed.
- Local preview startup/loopback gates: 4 passed.
- Preview identity login and mutation/external-route denial: 2 passed.
- `py_compile` for affected runtime modules: passed.
- `git diff --check`: passed.

No source export, Supabase connection, production operation, Secret access, deployment or notification was performed.
