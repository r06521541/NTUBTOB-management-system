# TASK-120: Staging runtime residue compatibility

task_type: delivery
delivery_group: mobile-staging-officer-acceptance
requires_independent_pr: true
status: ready_for_codex
base_commit: a79ffc6234e25645fe431c7774ef19b50fb733d4

## Goal

Unblock TASK-119 after accepted TASK-115 runtime activity left legitimate
fictional attendance and durable mobile-security history. Repair only the two
proven attendance rows and let the Officer operator validate, but never delete,
security records owned by the exact fictional tester.

## Exact evidence and repair boundary

- Canonical reply rows remain IDs `-112003`, `-112002`, `-112001` at
  `2000-01-01T00:00:00Z`.
- The only accepted TASK-115 residue is ID `3`, Game/Person `-112001`, reply
  `5`, `2026-08-19T16:33:02.723958Z`, followed by ID `4`, the same Game/Person,
  reply `1`, `2026-08-19T16:36:23.695486Z`; both owner columns are null.
- Inspection is read-only. Execution deletes exactly IDs `3` and `4` in one
  transaction with every column and timestamp in the `WHERE` predicate,
  requires rowcount two, and postchecks the canonical seeded fixture. Any
  near-miss or additional attendance row fails closed without mutation.

## Mobile-security invariant

- Existing counts `1/8/7/1/2` for session, refresh token, refresh attempt,
  auth exchange and idempotency records are accepted evidence of TASK-115
  lifecycle activity, not cleanup targets.
- Officer inspect/grant/restore may accept non-empty mobile tables only when
  every session belongs to auth identity and Person `-112001`, every child row
  joins to such a session, every idempotency row belongs to Person `-112001`,
  and every exchange is LINE. Cross-principal, orphan or malformed ownership
  fails closed.
- The operator does not read, print, hash, compare, update or delete token,
  assertion, attempt, installation or encryption payloads. It does not claim
  durable provenance beyond relational ownership.

## Scope and verification

- Modify only the staging data operator, its direct tests, mobile staging
  runbook, TASK-120 report and handoff/review documents.
- Add absent/exact/near-miss/additional-row repair tests; ownership tests for
  linked and cross-principal mobile history; retry and transaction rollback;
  PostgreSQL 15/16 hosted evidence plus affected offline regressions.
- No schema, API, Flutter, production, Secret, IAM, notification or staging
  execution in the repository slice.

## Execution checkpoint

1. Goal: restore the exact fictional attendance fixture without deleting mobile security history.
2. Core files: staging data operator, direct tests, runbook and one report.
3. Invariant: exact two-row repair; mobile history is ownership-checked and immutable.
4. Tests: near-miss rollback, cross-principal denial, retry, PG15/16 and regressions.
5. Blocker: no Owner blocker for repository work; staging execution waits for merge.
