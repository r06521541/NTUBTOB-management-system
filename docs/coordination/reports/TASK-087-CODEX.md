# TASK-087 Codex report

## Implementation

- Branch: `codex/activate-existing-linked-players`
- Base: `92592c08ae874370fee4be8e2e073636965383f9`
- Implementation commit: `0aa2adf34f0753ac720477c51861e8acef9eaa73`

Added independently checksummed, fixed-schema discovery/operator and launcher
artifacts for the existing reliably linked team-player cohort. The cohort size
is discovered from current relationships and is never fixed to the historical
expectation. Exactly two allowlisted, already-active administrators must remain
valid unchanged controls.

Under the existing advisory lock, the operator deterministically locks all
active team-player Persons and requires one Member, one non-ignored legacy LINE
row, and one linked LINE identity pointing to the same Person. It rejects
disabled, blocked, pending, wrong-Person, orphan, duplicate, mixed, partial, or
ambiguous state. A single transaction changes only eligible inactive Person
status/version/timestamp fields and adds one null-actor `status_changed` audit
with a fresh opaque request ID per Person. Member, identity, legacy LINE,
qualification, and attendance counts must remain unchanged.

Completed state is accepted only when the entire cohort is active and every
cohort Person has the exact TASK-087 audit shape. It then performs a verified
zero-delta retry; partial completion and malformed audits stop without repair.
The launcher reuses and checksum-locks the reviewed runtime/git/GCP metadata,
private PG, logging, and unconditional cleanup boundaries. It has the sole
sequence `discovery -> preflight -> execute -> post-check`, and emits only the
fixed redacted aggregate schema.

## Verification

- Offline TASK-087 contracts: 7/7 passed.
- TASK-087 plus directly reused exact-two offline contracts: 14/14 passed.
- Local isolated `postgres:15.8-alpine`: TASK-087 6/6 and adjacent exact-two
  regression 6/6 passed.
- Local isolated `postgres:16.4-alpine`: the same 12/12 passed.
- PostgreSQL coverage includes dynamic discovery, exact success and aggregate
  deltas, exact zero-delta retry, relationship drift, partial-completion audit
  rejection, injected partial failure rollback, unsafe logging, and two-session
  concurrency with one application and one verified retry.
- Python compileall, Black 24.4.2 formatter API, canonical artifact/material
  checksum verification, real-runtime safe stop, and `git diff --check`: passed.
- Both TASK-087 local PostgreSQL containers were stopped after testing.

## Limits and external operations

This implementation and all verification were repository/local only. No
gcloud command, private environment or Secret access, production connection or
DML, deployment, schema/cloud mutation, notification, or production activation
was performed. Production discovery/execution remains blocked until Work
acceptance, one ready PR, hosted PostgreSQL 15/16 CI, and squash merge. The
untracked Work-owned `docs/planning/ENGINEERING_HARDENING_NOTES.md` was preserved
and excluded from this task's implementation commit.

## Changes-requested correction: approved dynamic cohort boundary

- Correction commit: `6b7449a9d4a15b373b92b8ba796963f03faaab04`

Split the production boundary into two invocations. The independently
checksummed discovery launcher has one read-only, repeatable-read database path,
never sets the execution acknowledgement, and can only call `discovery`. The
separate execution launcher accepts one explicit positive, non-secret
`--approved-cohort-count`; its `preflight -> execute -> post-check` sequence
passes that count to every phase. Execute revalidates the exact count under the
same advisory lock and deterministic Person row locks before any Person or audit
write. Missing, invalid, stale, or mismatched counts stop with zero mutation.

Correction verification:

- TASK-087 plus adjacent exact-two offline contracts: 16/16 passed, including
  real-runtime safe-stop subprocesses for both launchers, discovery no-ack/no-
  execute behavior, CLI argument rejection, and fixed cleanup/output.
- Local isolated PostgreSQL 15.8 and 16.4: TASK-087 7/7 on each version,
  including explicit read-only discovery and missing/wrong/drifted approved
  count with unchanged Person/audit/relationship aggregates.
- Before the final read-only transaction adjustment, both versions also passed
  the combined TASK-087 plus adjacent exact-two matrix 13/13; the final TASK-087
  7/7 rerun is the authoritative evidence for the corrected code.
- Compileall, Black 24.4.2 formatter API, canonical checksums, fixed safe-stop
  subprocesses, and `git diff --check`: passed.

No external or production operation was performed during this correction.
