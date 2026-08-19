# TASK-118: Staging attendance fixture time and uncertain recovery

task_type: delivery
delivery_group: mobile-staging-activation
requires_independent_pr: false
status: active
base_commit: d87b58de2de6d03dca9ec92ebb40b2b535cc53db

## Goal

Repair the fictional mobile staging attendance fixture whose future-dated
`updated_at` hides runtime replies, then safely reconcile the two bounded
TASK-115 uncertain attempts. Keep schema revision 0005 and production untouched.

## Root cause and required behavior

- The TASK-112 seed uses `2035-01-10` for the original attendance row while the
  runtime writes the actual current time. Latest-reply reads therefore keep
  selecting the fixture's `attending` row after a new `undecided` row commits.
- Seeded reply timestamps must be deterministic and strictly earlier than the
  seed execution time. Future game start times may remain future-dated.
- Existing staging data needs an exact, ownership-checked repair. It may update
  only the TASK-112 fictional reply rows and remove only the two proven hidden
  TASK-115 test rows for Person/Game `-112001`; unknown drift must fail closed.
- After repair, the existing `attending` state is authoritative. A fresh-key
  fictional mutation may be tested only after repository, PG and hosted gates.

## Repository scope

- `tools/mobile_staging_seed.py` and the existing staging data operator/recovery
  path, with bounded tests and the mobile staging runbook/report.
- Add regression coverage proving a runtime reply outranks the fixture row,
  same-key recovery does not duplicate mutation, exact repair is retry-safe and
  drift/unknown rows are rejected.
- PostgreSQL 15/16 integration starts from the true repository bootstrap and
  fixture state. Existing mobile API, Web and TASK-106 regressions must pass.

## Writer and operational boundary

- Shared/Web Codex is the sole implementation writer in an independent
  worktree/branch. Main Work owns this task, global coordination, review, PR,
  merge, staging data execution, deployment and Flutter re-acceptance.
- Revision remains `0005_mobile_auth_api_foundation`; no migration/model/schema,
  production, Secret payload, IAM, LINE Console or notification changes.
- Staging fictional build/deploy/data repair/rollback are covered by the Owner's
  standing staging authorization. Unknown data, production-shaped identity,
  new cost/public access or destructive resource deletion still stop.

## Verification

- Unit contracts for timestamp ordering, exact repair, retry and drift denial.
- PostgreSQL 15/16 true-fixture integration and idempotency recovery.
- Mobile API/shared affected suites, compile, Black/isort and diff checks.
- Hosted final gate, exact staging repair postcheck, one controlled Flutter
  mutation/readback/restore, then TASK-115 source closeout.

## Execution checkpoint

1. Goal: make fictional attendance mutation authoritative and recover the two uncertain attempts.
2. Core files: staging seed/data operator, tests, runbook and one task report.
3. Invariants: revision 0005, exact fictional ownership, no notification/production/Secret payload.
4. Tests: timestamp ordering, same-key recovery, PG15/16, mobile regressions and hosted CI.
5. Blockers: none; unknown staging rows or non-exact repair state fail closed to Main Work.
