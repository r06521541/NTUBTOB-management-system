# TASK-119: Fictional staging Officer acceptance

task_type: delivery
delivery_group: mobile-staging-officer-acceptance
requires_independent_pr: true
status: ready_for_hosted_ci
base_commit: d4569577817a18e74758dad61bfaff2b82991f85

## Goal

Close the staging-only acceptance gap for the existing mobile Officer
read-only attendance report. Add a fail-closed, reversible operator that
temporarily changes only the already-linked fictional staging tester from
Basic to Officer, proves the server capability/report boundary, then restores
the active Basic fixture state.

## Repository scope

- Extend the existing mobile staging data/operator path and its tests; update
  the mobile staging runbook and this task's single Codex report.
- The operator accepts only revision `0005`, the exact TASK-112/TASK-118
  fictional fixture, the exact linked tester identity and task-owned append-only
  access-audit transitions. It provides inspect, grant, restore and recovery
  states without ad-hoc SQL instructions.
- Use the existing mobile API/OpenAPI and Flutter client unchanged unless a
  reproducible defect requires a separately scoped correction.

## Invariants

- The only mutable Person is `-112001`; its normal state is active Basic. The
  only temporary state is active Officer with exactly the task-owned grant
  audit. Restored state is active Basic with exactly one task-owned grant and
  one task-owned restore audit. All other fixture rows, identities, qualifications, games,
  replies and non-fixture rows fail closed on drift.
- `access_audit` is schema-enforced append-only. Restore returns the Person to
  Basic and verifies the bounded audit pair and version as the semantic fixture
  baseline. It never deletes audit/data, changes schema, creates an admin,
  changes production, exposes Secret values or sends a notification.
- Staging operations follow DEC-098: agent may perform bounded fictional
  inspect/grant/restore after repository acceptance; any unknown state is
  read-only reconciled and stops.

## Delivery slices

1. Repository operator and regression tests, including true-fixture PostgreSQL
   evidence and fail-closed near-miss cases.
2. Main review, final PR and hosted CI.
3. Staging execution and mobile API report smoke using the existing fictional
   tester. Owner performs only the next LINE consent/login; agent performs
   navigation, read-only report checks, downgrade/cache-purge verification and
   restoration.

## Verification

- Operator unit contracts for baseline, grant, restore, retry and drift
  denial; PostgreSQL 15/16 fixture integration where available.
- Mobile API capability/report regression and existing Flutter hosted final
  gate for any client change.
- Redacted staging inspect → grant → report → restore postchecks. Basic must
  never receive the report route or cached Officer data after downgrade.

## Execution checkpoint

1. Goal: demonstrate bounded Officer read parity on fictional staging and leave the baseline intact.
2. Core files: mobile staging operator/data tests, runbook and TASK-119 report.
3. Invariants: exact fixture ownership, reversible Basic↔Officer only, no schema/production/notification.
4. Tests: drift denial, grant/restore/retry, PG fixture integration and mobile capability regression.
5. Blocker: runtime login consent is Owner-only; repository implementation has no Owner blocker.
