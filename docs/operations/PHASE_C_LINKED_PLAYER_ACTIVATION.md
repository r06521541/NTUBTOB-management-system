# Phase C existing linked-player activation

This package activates only the complete cohort of existing inactive Persons
whose legacy Member, non-ignored LINE row, linked LINE identity, and active
team-player qualification form one exact relationship. It does not assume the
historical expected count of 54. The two allowlisted active administrators are
unchanged controls.

Production execution is permitted only after Work acceptance, one ready PR,
hosted PostgreSQL 15/16 CI, and squash merge. It has two separate invocations.
From a clean repository root, first set only the non-secret merged SHA as
`TASK087_APPROVED_MERGED_COMMIT` and run the independently checksummed,
read-only discovery launcher:

```powershell
& "C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" tools/launch_production_discover_linked_players.py
```

The discovery invocation cannot set the execution acknowledgement or call the
execute mode. Record only its fixed redacted `eligible_cohort_count`; Work and
Owner must explicitly approve that positive count. Do not continue on missing,
ambiguous, unexpected, or unapproved output.

Only after that approval, pass the approved non-secret aggregate count to the
separate execution launcher exactly once. The example placeholder must be
replaced with the approved positive integer:

```powershell
& "C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" tools/launch_production_activate_linked_players.py --approved-cohort-count <APPROVED_POSITIVE_COUNT>
```

The launcher reuses the reviewed exact runtime/dependency/git,
account/project/service/region, in-memory Cloud Run env metadata, private PG,
logging, and cleanup boundaries. The execution launcher's only sequence is
`preflight -> execute -> post-check`; only execute receives the fixed internal
acknowledgement. It revalidates the approved count under the advisory and row
locks before any write. The approved aggregate count is non-secret and is the
only task value accepted through argv. Database URL, allowlist, identifiers,
request IDs, metadata, and credentials never enter argv or output.

Discovery reports only fixed redacted aggregates: the dynamically proven
eligible cohort count, exactly two active controls, and zero drift. Under the
existing advisory lock, the operator deterministically locks every active
team-player Person and requires one Member, one non-ignored legacy LINE row,
one linked LINE identity pointing to the same Person, and a safe Person status.
It rejects missing, wrong-Person, orphan, duplicate, pending, disabled, blocked,
mixed, partial, or ambiguous state.

One transaction changes only eligible Persons from inactive to active,
increments version, updates timestamp, and inserts one null-actor
`status_changed` audit per Person with the fixed batch reason and a fresh
internal request ID. Exact post-checks require inactive -N, active +N, audits
+N, both controls unchanged, and unchanged Member, identity, legacy LINE,
qualification, and attendance cardinalities. An exact completed audit set is a
zero-delta idempotent retry; partial completion is rejected, never repaired.

Missing, non-positive, or mismatched approved count stops before DML. Do not
rerun after uncertain output or connection loss. Any drift, unsafe
logging, exception, aggregate mismatch, or concurrency ambiguity must stop and
roll back the entire batch. No ad-hoc SQL repair, deployment, notification,
schema, identity, Member, LINE-link, qualification, or attendance mutation is
authorized by this package.
