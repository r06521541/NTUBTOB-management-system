# TASK-086 activate two existing allowlisted administrators

## Goal

Activate both existing allowlisted administrators whose LINE identities are already correctly linked, without changing identity, Member, LINE-link or qualification relationships.

## Confirmed production state

- Base commit: `323bf95d1bf412b725ac99844c95a4724c96bdec`.
- The Owner confirmed `WEB_PORTAL_ADMIN_MEMBER_IDS` intentionally contains exactly two Member IDs and approved activating both.
- Owner-run read-only aggregate SQL returned: two matched Members; zero missing Persons; two inactive Persons; zero active/pending/disabled/blocked Persons; two non-ignored legacy LINE links; two linked LINE identities pointing to the same corresponding Person; zero linked-other-Person; two active team-player qualifications; zero pending-unlinked candidates.
- The reviewed production diagnostics confirm all runtime/metadata/private-PG/connection/schema/read-logging guards pass, zero active linked allowlisted admins, and zero prior bootstrap audit/result.

## Owner authorization

On 2026-08-10 the Owner explicitly approved activating both allowlisted Persons. Authorization includes repository implementation, local/isolated tests, one ready PR, hosted CI, squash merge, one exact production transaction and read-only verification. It does not authorize schema/DDL, deployment, Secret payload access, IAM/Scheduler/flags/traffic changes, notifications, identity/Member/LINE-link/qualification mutation, ad-hoc repair or the separate 56-Person activation.

## Required transaction

1. Reuse the reviewed exact runtime/git/checksum/account/project/service/region, strict in-memory env metadata, private PG, logging and cleanup boundaries.
2. Fail closed unless the allowlist contains exactly two unique positive Member IDs and both still satisfy every confirmed relationship above.
3. In one database transaction and under the established advisory-lock boundary, lock both Person rows in deterministic order.
4. Change only each Person's `portal_status` from `inactive` to `active`, increment version and update timestamp according to existing lifecycle conventions.
5. Insert exactly two `status_changed` audit rows, one per Person, with null actor (zero-admin bootstrap), exact before/after state, fixed reason and two fresh internal opaque request IDs. No identifier or request ID may be printed or persisted outside the database audit.
6. Any failure must roll back both status changes and both audits. A safely classified retry must be idempotent and must not create additional audit rows.
7. Fixed redacted output and post-check must prove exact deltas: inactive -2, active +2, audit +2; all identity, Member, legacy link, qualification and attendance aggregates unchanged; two active linked allowlisted administrators.

## Verification

- Offline no-disclosure/checksum/structural launcher tests.
- Isolated PostgreSQL 15/16 success, relationship-drift rejection, partial-failure rollback, concurrency and idempotent retry tests.
- Hosted PostgreSQL 15/16 and final gate on one ready PR.

## Production execution and stop boundary

After squash merge, execute the exact merged transaction once. Do not rerun on uncertain output or connection loss. Follow with an independently read-only exact-two post-check. Stop without ad-hoc repair if any guard, relationship, delta, audit or aggregate differs. Only after exact success may Work close TASK-086 and create the separate 56-Person activation task.
