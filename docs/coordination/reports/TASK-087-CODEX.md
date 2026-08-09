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
