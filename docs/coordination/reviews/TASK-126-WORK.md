# TASK-126 Work review

## Decision

Accepted for hosted CI. PostgreSQL 15 remains the only unverified matrix cell.

## Findings

- Role ownership is a complete alternating audit chain. Legacy TASK-119 rows
  remain accepted; later transitions append deterministic, version-bound audit
  records without updating or deleting history.
- Attendance reset is restricted to rows whose Person and Game are both in the
  reserved fictional fixture. Canonical-ID collision, one-sided ownership and
  malformed reply state fail closed before mutation.
- Reset reclassifies inside a serializable transaction, locks the fixture roots,
  restores Officer to Basic when necessary, reconstructs only owned attendance,
  and independently postchecks the canonical relation before commit.
- Mobile session, refresh, exchange and idempotency tables are read only through
  aggregate/FK ownership checks. Cross-principal/provider/binding drift is
  rejected; no payload, token or hash material is selected or emitted.
- Existing TASK-118/120 repairs and TASK-119/121 bounded contracts remain
  compatible. No schema, seed, runtime API, Flutter or cloud scope was added.

## Evidence

- Writer affected offline suite: 51 passed; 21 PostgreSQL tests skipped without
  a database URL.
- Writer local PostgreSQL 16.2 matrix: 21 passed, including repeat generations,
  append-only/mobile-history preservation, relational reset and rollback.
- `py_compile`, isort and `git diff --check` passed. PostgreSQL 15 and Black are
  intentionally deferred to hosted CI because the local runtimes were
  unavailable/stalled.
- Main delta review inspected the audit chain, mobile ownership graph, reset
  transaction and destructive SQL boundary. The only attendance DELETE requires
  both reserved fixture Person and Game and excludes canonical IDs.

## Remaining gate

- Run the selected hosted portal-data/deployment gates, including PostgreSQL 15
  and 16. Do not execute the staging reset as part of CI.
