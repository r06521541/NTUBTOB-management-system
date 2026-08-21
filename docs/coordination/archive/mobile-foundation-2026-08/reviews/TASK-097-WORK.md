# TASK-097 Work Review

status: accepted
reviewer: work
reviewed_at: 2026-08-10T09:59:08+08:00
branch: codex/phase-d-local-cloud-data-preview
implementation_commit: f4c0aa7c5cc552f02df288132e774024dabc4220

## Review result

Accepted for the delivery group's single final PR after correction. The security gates, private-bundle validation,
pseudonymization, exact local-fixture replacement and isolated PostgreSQL evidence satisfy TASK-097 without authorizing
or performing a source export.

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

## Correction verification

Resolved by implementation commit `71e6e0dd4ef70fe7f99d566570d8c9307a3ea281`:

- The importer fingerprints only the exact repository-owned setup＋0004 fixture and replaces it in the same transaction
  as the derived bundle import; truly empty databases remain accepted and every other non-empty／drifted state is denied.
- PostgreSQL tests now create the real legacy fixture, stamp `0001_legacy_baseline`, and upgrade to
  `0004_phase_c_identity_lifecycle`; the successful path no longer calls a test-only pre-import truncate.
- PostgreSQL 15.8 and 16.4 each passed success/readback, arbitrary drift denial, late-failure fixture restoration and
  corrected retry (`3/3` per version).
- Work re-ran the five offline bundle/security tests plus `py_compile` and `git diff --check`; all passed. PostgreSQL
  integration was reviewed from the actual test diff and Codex's isolated-version evidence rather than rerun by Work.

## Work targeted verification

- `LocalPreviewBundleTest`: 5 passed.
- Local preview startup/loopback gates: 4 passed.
- Preview identity login and mutation/external-route denial: 2 passed.
- `py_compile` for affected runtime modules: passed.
- `git diff --check`: passed.

No source export, Supabase connection, production operation, Secret access, deployment or notification was performed.

## Hosted CI correction and final evidence

PR #107 initially exposed one packaging defect across the Web Portal and both PostgreSQL jobs: repository-checkout tests
could not resolve the packaged `shared_module` namespace. Commit `f4c0aa7c5cc552f02df288132e774024dabc4220`
corrected the context-specific import contract without copying or weakening `require_local_database_url`:

- repository tooling imports through `shared_lib.shared_module`;
- Web Portal runtime code remains on its deployed `shared_module` namespace, while checkout tests add the repository
  package root only to their own `sys.path`／subprocess `PYTHONPATH`;
- the deployed Web Portal shared-library archive contains `shared_module/portal_data/local_database.py`.

Hosted Python 3.10 run `31348466658` then passed Web Portal, PostgreSQL 15.8, PostgreSQL 16.4, formatting／artifact
checks and the CI final gate. Work inspected the correction diff and accepts TASK-097 for squash merge.
