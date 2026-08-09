# TASK-086 zero-admin candidate-state diagnostic

## Goal

Determine why the reviewed production bootstrap launcher stops before applying any mutation, without exposing identifiers or changing production state.

## Confirmed state

- Base commit: `93cbbe598d3e4031786f83653d54ca9e5a6bd551`.
- PR #95 passed hosted CI and merged; the exact recovery launcher returned fixed stop / exit 1.
- The immediately following reviewed diagnostic returned all guards `pass`, `active_admin=zero`, `completed_relationship=zero`; therefore no bootstrap mutation was applied.
- Environment, Cloud Run metadata, private PG, connection, schema and read-logging guards are confirmed healthy.

## Owner authorization

The Owner approved one repository-reviewed, fixed-schema production read-only candidate diagnostic. It may read the existing allowlist through the reviewed in-memory metadata boundary and query production only in an explicit read-only transaction. It does not authorize DDL/DML, a bootstrap retry, 56-Person activation, Secret payload access, deployment, IAM/Scheduler/flags/traffic changes or notifications.

## Required classifications

Return only fixed enum/count classifications sufficient to distinguish, without identifiers:

- runtime/metadata/private-PG/connection/schema/read-logging guards: `pass|fail`;
- allowlisted legacy Member candidates: `zero|one|other`;
- corresponding Person state: `absent|inactive|active|blocked|other`;
- reliable LINE identity relationship: `none|pending_unlinked|linked_same_person|linked_other_person|other`;
- eligible pending review-thread candidates: `zero|one|other`;
- matching legacy LINE link: `zero|one|other`;
- active team-player qualification: `zero|one|other`;
- relevant bootstrap audit: `zero|one|other`.

Codex may refine enum names only if needed to match executable domain semantics, but output must remain fixed, redacted and sufficient to select one safe recovery path.

## Engineering boundaries

1. Build an independently checksummed diagnostic; do not call the five-stage launcher, bootstrap operator, lifecycle mutation repository, request-ID generation or any write path.
2. Reuse only the reviewed runtime/artifact/git/account/project/service/region, strict in-memory env metadata, private PG and cleanup guards.
3. Use `SET TRANSACTION READ ONLY` and local statement/lock/idle timeouts; SQL must contain SELECT-only classification queries.
4. Never print/log/persist raw Member IDs, LINE IDs, Person IDs, names, allowlist values, DB values, SQL parameters, metadata or exception text.
5. Add adversarial and isolated PostgreSQL 15/16 tests for the possible relationship states and failure cleanup.

## Delivery and production execution

After Work acceptance, one ready PR, required hosted CI and squash merge, execute the exact diagnostic once. The result returns to Work/Owner for selection of a new exact recovery transaction. Do not mutate production within this task.
