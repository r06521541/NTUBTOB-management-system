# TASK-175 Data/Auth review

## Verdict

`ACCEPT`

- Reviewer: `/root/task170_release_security_review`
- Claim: `task-175-data-auth-review-20260901`
- Final lease: 4
- Accepted immutable implementation: `e64c915e50b409d0c924503e00689f0eaf518a73`

## Accepted boundaries

- Event notifications derive recipients only from the immutable included-invitee snapshot, require preview and explicit confirmation,
  and create durable in-app history without push or external delivery work.
- Guest-player mutations use stable active Persons, exact version/replay/audit rules and the narrow Officer or allowlisted-admin surface;
  legacy generic qualification routes cannot grant or revoke guest state.
- Person status mutation and Event recipient selection use `ADMIN advisory -> EVENT advisory -> actor row -> target row`, avoiding the
  reviewed actor-row/advisory deadlock while excluding disabled recipients on the next serialized preview.
- Basic projections expose only the caller's immutable participation category and received notification, not recipients or audit data.
- The additive 0011 migration remains a single linear head and retains audit/notification evidence on downgrade.

## Evidence

- Reviewer focused portal lifecycle: 49 passed, 38 expected isolated-PostgreSQL skips.
- Reviewer Web security: 144 passed.
- Reviewer Event/Mobile compatibility: 55 passed.
- `py_compile`, `git diff --check`, and single Alembic-head checks passed.
- Writer affected-full evidence is recorded in `docs/coordination/reports/TASK-175.md`.

## Remaining limit

No isolated PostgreSQL URL was available locally. The real competing-transaction, rollback, migration and PostgreSQL-version matrix are
required hosted CI evidence. No cloud, provider, runtime, production data or real notification mutation was performed.
