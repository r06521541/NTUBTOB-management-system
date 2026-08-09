# TASK-087 activate existing reliably linked team players

## Goal

Activate the remaining existing Persons who already have a trustworthy Member, LINE and active team-player relationship, completing the Phase C transition for the legacy linked cohort without requiring each player to visit the Portal first.

## Base and known state

- Base commit: `92592c08ae874370fee4be8e2e073636965383f9`.
- The last controlled inventory found 56 reliable linked LINE identities and 56 active team-player qualifications with no listed identity/Member/qualification drift.
- TASK-086 has now activated the two allowlisted administrators with exact audited deltas. The expected remaining inactive cohort is therefore 54, but this task must discover and prove the exact count rather than assume it.

## Owner authorization

The Owner previously authorized continuous completion through administrator activation, verification and processing the existing 56 linked players, and on 2026-08-10 instructed Work to continue after TASK-086 succeeded. This authorizes repository implementation, local/isolated tests, one ready PR, hosted CI, squash merge, one exact production batch transaction and read-only verification for the safely discovered cohort. It does not authorize schema/DDL, deployment, Secret payload access, IAM/Scheduler/flags/traffic changes, notifications, identity/Member/LINE-link/qualification/attendance mutation, or unrelated Persons.

## Eligibility contract

A Person is eligible only when all are true at execution time:

- exactly one legacy Member points to the Person;
- exactly one non-ignored legacy LINE row points to that Member;
- exactly one LINE auth identity for that provider subject is `linked` to the same Person;
- the Person has exactly one active `team_player` qualification;
- the Person's `portal_status` is `inactive`;
- the identity and Person are not disabled or blocked;
- there is no wrong-Person, orphan, duplicate or pending-unlinked relationship for the cohort.

The two already-active allowlisted administrators are excluded from mutation but must remain valid unchanged controls.

## Required implementation

1. Add an independently checksummed fixed-schema discovery/preflight that reports only aggregate classifications and proves the exact eligible cohort (expected 54), active control count (expected 2), and zero drift.
2. Reuse the reviewed runtime/git/checksum/account/project/service/region, strict in-memory env metadata, private PG, logging and cleanup boundaries.
3. Under one advisory lock and deterministic Person row locks, revalidate the entire cohort and controls inside one transaction.
4. Change only eligible Person rows from `inactive` to `active`, increment version and update timestamp using existing conventions.
5. Insert exactly one null-actor `status_changed` audit per activated Person with fixed batch reason, exact before/after state and fresh opaque internal request ID. Never output IDs or request IDs.
6. Transaction must be all-or-nothing. Partial failure, drift, unsafe logging or aggregate mismatch rolls back every Person and audit change.
7. Completed state must support an exact idempotent verified retry with zero new audits. Reject partial completion rather than repairing it.
8. Fixed redacted post-check must prove exact cohort/audit deltas, all eligible Persons active, both administrator controls unchanged, and identity/Member/legacy LINE/qualification/attendance aggregates unchanged.

## Verification

- Offline no-disclosure, checksum, structural and launcher tests.
- Isolated PostgreSQL 15/16 discovery, success, drift rejection, partial rollback, idempotency and concurrency tests using fictional data.
- Required hosted PostgreSQL 15/16 and final gate on one ready PR.

## Stop boundaries

Do not execute production mutation unless discovery proves one exact complete cohort with zero drift and the repository package has passed Work review, hosted CI and squash merge. Execute only once. On uncertain output, connection loss, partial state or post-check mismatch, do not rerun or perform ad-hoc SQL repair; return to Owner with fixed redacted evidence.
