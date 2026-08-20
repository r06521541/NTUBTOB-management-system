# TASK-120 Codex Report

## Scope

Implemented a repository-only, fail-closed repair for the two task-defined
TASK-115 fictional attendance residues. No staging, cloud, database, Secret,
LINE, notification, production, schema, migration, model, mobile API, or Flutter
operation was performed.

## Implementation

- Added read-only `--inspect-runtime-residue` and candidate-gated
  `--execute-runtime-residue-repair` actions to the staging data operator.
- The executable state requires the complete canonical fixture plus exactly IDs
  `3` and `4` with the approved ownership tuples, replies, and UTC timestamps.
  Repair rechecks state, executes a single transaction with exact DELETE
  predicates, requires rowcount two, and postchecks the canonical baseline.
  An exact repaired state is a zero-delta retry.
- Preserved all `mobile_*` records. Officer inspection/transitions accept empty
  mobile history or only the documented runtime cardinalities (1/8/7/1/2) after
  ownership-only validation: every session/child join is linked to fictional
  identity and Person `-112001`, LINE is the sole exchange provider, and every
  idempotency record belongs to that Person. No token, assertion, attempt,
  installation, encrypted payload, or hash is inspected or emitted.
- Added PostgreSQL integration coverage for exact repair/retry, canonical
  readback, mobile-history immutability, Officer grant/restore after repair,
  timestamp/additional-row rejection, and cross-principal mobile-history
  rejection. A true orphan cannot be created through the production schema's
  foreign keys; count/join drift remains rejected before mutation.

## Verification

- Bundled Python with temporary, repository-pinned test dependencies:
  `python -m unittest tools.tests.test_mobile_staging_operator -q` — 35 passed,
  12 skipped (the skips are database integration tests when no URL is supplied).
- One-time local PostgreSQL 16 cluster:
  `python -m unittest tools.tests.test_mobile_staging_operator.EmptyDatabaseBootstrapIntegrationTest -q`
  — 12 passed, including exact repair, retry, rollback, timestamp/additional-row,
  mobile ownership, and Officer postcheck coverage.
- `python -m py_compile tools/mobile_staging_data.py tools/tests/test_mobile_staging_operator.py` — passed.
- `python -m isort --profile black --check-only ...` and
  `python -m black --check ...` — passed for the two changed Python files.
- `git diff --check` — passed.
- PostgreSQL 15 and hosted Python 3.10 remain final CI evidence. No staging or
  external database was contacted.

## Safety boundary

The runbook states that this is an exact, task-defined fixture-state repair, not
a provenance claim or broad reset. Process-only private tester input is not
printed or persisted. Unknown attendance rows, near-miss timestamps, mobile
ownership drift, and all non-fixture state fail closed.
