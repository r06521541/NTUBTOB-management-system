# TASK-065 Codex report

## Result

Status: `ready_for_review`

Implemented a repository-only Phase B inventory/backfill/post-check package and proved it against local PostgreSQL.
No production query or mutation, Secret access, deployment, notification, identity-by-name match, admin/officer
promotion, ignored-user conversion or Phase C work occurred.

## Behavior

- Every Member maps to one basic/inactive Person using only the Member primary key and `members.person_id`.
- Only non-ignored legacy LINE rows with an existing Member FK become linked LINE auth identities.
- Only those reliably linked Members receive active `team_player`; all other Members remain without that qualification.
- Multiple LINE accounts may map to the same Person; duplicate provider subjects and orphan Member links fail closed.
- The transaction uses 5-second lock timeout, 60-second statement timeout, a fixed advisory transaction lock and row
  locks. Re-running an exact successful batch is idempotent.
- Member, identity and qualification effects receive separate append-only audit rows with deterministic request IDs.
- Inventory and post-check output only fixed six-column booleans/counts/revision; no Member ID, LINE subject, name or
  row value is emitted.

## Verification

- `python -m unittest tests.portal_data.test_phase_b_artifacts -v`: 8/8 passed on local PostgreSQL 16.
- `python -m unittest discover -s tests/portal_data -v`: 116/116 passed on local PostgreSQL 16.
- Full backfill rerun preserved `(people, identities, qualifications, audits, linked members) = (2, 1, 1, 4, 2)`.
- Exact full transaction rendered with final rollback restored the zero-row Phase A fixture state.
- Non-batch Person drift failed closed without adding any further rows.
- Two LINE subjects linked to one Member produced two identities and exactly one qualification.
- `python -m tools.portal_data_phase_b verify`: passed.
- `python -m compileall -q shared_lib tools tests/portal_data`: passed.
- Black check for the two new Python files: passed.
- `git diff --check`: passed.

The machine has no global `python` command; validation used the Codex workspace bundled Python. This is an environment
detail, not a product failure. One intermediate rerun started before the container healthcheck completed and failed
with PostgreSQL `database system is starting up`; the final commands used Compose `--wait`, then passed and stopped the
container/network.

## Recovery limitation

Transaction rollback is exact only before commit. Once committed, the append-only `access_audit` trigger deliberately
prevents deleting this batch's audit rows. A production execution task must define forward compensation and must not
disable the trigger to manufacture an exact post-commit rollback claim.

## Not performed

- No production inventory CSV was generated or validated.
- No production backfill or rollback was run.
- No production credentials, `envs/**/.env.yaml`, IAM, Secret, RLS policy, service runtime or external API was used.
- No push, PR, merge or deployment.
