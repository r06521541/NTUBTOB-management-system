# TASK-120 Work review

## Decision

Accepted for hosted CI and final PR.

## Findings

- The repair accepts only the complete canonical fixture plus attendance IDs
  `3` and `4` with their exact ownership, replies and UTC timestamps.
- Execution rechecks in one transaction, deletes through complete predicates,
  requires exactly two rows and postchecks canonical state. Near misses and
  additional rows fail before mutation; exact repaired state is idempotent.
- Mobile session, refresh, exchange and idempotency history is never modified.
  Every table requires its total row count to equal rows joined to sessions for
  identity/Person `-112001`; exchanges must be LINE and idempotency rows must
  belong to the same Person.
- The initial fixed `1/8/7/1/2` implementation was rejected because a later
  Officer login would prevent restore. The accepted correction validates
  ownership dynamically and includes a second-session grant/restore test plus
  cross-principal/provider/idempotency denial tests.

## Evidence

- Codex: offline operator suite 39 passed with 16 database skips; isolated
  PostgreSQL 16 integration 16 passed; py_compile, Black, isort and diff check
  passed.
- Main Work: cumulative source and security review passed; py_compile and diff
  check passed after integration. Its bundled Python environment lacked
  Alembic for an independent unittest rerun, so hosted Python 3.10 and
  PostgreSQL 15/16 remain mandatory final evidence.

## Deferred

No staging, cloud, Secret or external database operation occurred. Runtime
repair and TASK-119 Officer acceptance remain paused until this PR merges.
