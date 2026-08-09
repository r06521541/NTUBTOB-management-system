# Phase C existing linked-player activation

This package activates only the complete cohort of existing inactive Persons
whose legacy Member, non-ignored LINE row, linked LINE identity, and active
team-player qualification form one exact relationship. It does not assume the
historical expected count of 54. The two allowlisted active administrators are
unchanged controls.

Production execution is permitted only after Work acceptance, one ready PR,
hosted PostgreSQL 15/16 CI, and squash merge. From a clean repository root, set
only the non-secret merged SHA as `TASK087_APPROVED_MERGED_COMMIT`, then run the
checksummed launcher exactly once:

```powershell
& "C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" tools/launch_production_activate_linked_players.py
```

The launcher reuses the reviewed exact runtime/dependency/git,
account/project/service/region, in-memory Cloud Run env metadata, private PG,
logging, and cleanup boundaries. Its only sequence is `discovery -> preflight
-> execute -> post-check`; only execute receives the fixed internal
acknowledgement. Database URL, allowlist, identifiers, request IDs, metadata,
and credentials never enter argv or output.

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

Do not rerun after uncertain output or connection loss. Any drift, unsafe
logging, exception, aggregate mismatch, or concurrency ambiguity must stop and
roll back the entire batch. No ad-hoc SQL repair, deployment, notification,
schema, identity, Member, LINE-link, qualification, or attendance mutation is
authorized by this package.
