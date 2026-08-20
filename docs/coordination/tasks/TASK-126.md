# TASK-126: Relational staging fixture lifecycle

- Task type: repository implementation
- Delivery group: `mobile-staging-acceptance-automation`
- Requires independent PR: false
- Status: ready for hosted CI
- Operator: agent under DEC-098
- Owner gate: none for repository work

## Goal

Replace fixed attendance row-count/timestamp and Person version 1/2/3 cleanup
assumptions with a repeatable relational lifecycle for the reserved fictional
mobile fixture. Preserve append-only security/session/audit history and reset
only fixture-owned, reconstructible state.

## Scope and ownership

One implementation writer owns:

- `tools/mobile_staging_data.py`
- `tools/tests/test_mobile_staging_operator.py`
- `docs/operations/mobile/MOBILE_STAGING.md`
- one TASK-126 report

Seed, models, migrations, launcher, Flutter, runtime API, global coordination,
cloud and staging execution are out of scope. Existing files are read-only
dependencies unless this task explicitly owns them above.

## Invariants

- No migration: use reserved fixture Person/auth-identity/game relations,
  generated audit identity, unique request ID, append-only audit, and existing
  mobile child foreign keys.
- A valid role lifecycle is a complete alternating Basic <-> Officer audit
  chain whose target, linked identity, before/after role and monotonic Person
  version all agree. Existing TASK-119 baseline/grant/restore states are legacy
  generation zero and remain accepted.
- Future request IDs are deterministic bounded lifecycle IDs derived from the
  prior version and transition. Historical audit rows are never updated or
  deleted.
- Fixture attendance ownership is derived from reserved Person/game relations,
  not row ID, timestamp or total count. Canonical ID collision, partial
  ownership, or cross-fixture relation fails closed before mutation.
- Mobile sessions/exchanges/refresh/idempotency are validated by their full FK
  ownership graph. They are never read for payload/hash material and never
  modified or deleted. Cross-principal/provider/binding drift fails closed.
- Inspect uses a read-only transaction and returns only bounded
  `ready_basic`, `ready_officer`, or `reset_required`. Unknown state is drift.
- Reset reclassifies under a serializable transaction and locks fixture roots.
  A valid Officer generation appends one restore audit and increments Person
  version; valid Basic does not mutate role. It removes relationally-owned
  noncanonical attendance and reconstructs canonical values without timestamp
  preconditions.
- Postcheck uses relational `NOT EXISTS`/canonical-value assertions, not fixed
  affected-row counts. Completed reset is zero-change success. Serialization or
  unknown outcome requires fresh read-only inspect, never blind retry.
- Existing `--inspect-officer`, `--grant-officer`, `--restore-basic`, TASK-118,
  TASK-120 and TASK-121 public bounded output contracts remain compatible.
  TASK-121 accepts any valid active Officer generation, not only version 2.

## Acceptance

1. Add mutually exclusive `--inspect-fixture-lifecycle` and candidate-gated
   `--reset-fixture-lifecycle` actions with stable redacted output.
2. Classify legacy v1/v2/v3 and arbitrary later valid generations; reject audit
   gaps, duplicates, wrong order/JSON/request IDs and unknown target audits.
3. Reset arbitrary fixture-owned attendance IDs/timestamps/counts; reject
   partial ownership and canonical collisions; retry after success is zero
   change.
4. Preserve arbitrary valid mobile history byte-for-byte while rejecting
   cross-principal/provider/binding drift.
5. PostgreSQL 15/16 each prove two grant/restore generations, monotonic Person
   version, append-only audit, dynamic attendance reset, rollback on drift and
   legacy TASK-118/120/121 compatibility.

## Verification budget

- Writer: one affected offline suite and one PG15/16 integration matrix.
- Domain reviewer: targeted relational ownership/audit-chain tests only.
- Main Work: delta-only review of reset boundaries and compatibility.
- Hosted CI: one final deployment/portal-data gate as selected by change
  detection. Same-SHA infrastructure retry is not another product round.

## Five-line execution checkpoint

1. Goal: make the fictional staging fixture safely repeatable without deleting history.
2. Files: data operator, direct tests, mobile runbook, one report.
3. Invariants: relational ownership, append-only audit, mobile history untouched, unknown drift stops.
4. Tests: offline ownership matrix plus one PG15/16 lifecycle matrix.
5. Blockers: none; schema expansion or ambiguous ownership stops and returns to Main.
