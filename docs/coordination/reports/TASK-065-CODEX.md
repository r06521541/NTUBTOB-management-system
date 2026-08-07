# TASK-065 Codex report

## Result

Status: `ready_for_review`

The first Work review requested stricter fail-closed evidence and inventory binding. This revision addresses all four
blocking findings: explicit per-metric schemas, complete Phase A boundary gates, validated-inventory rendering with
execution-time drift checks, and exact audit relationship checks.

Implemented a repository-only Phase B inventory/backfill/post-check package and proved it against local PostgreSQL.
No production query or mutation, Secret access, deployment, notification, identity-by-name match, admin/officer
promotion, ignored-user conversion or Phase C work occurred.

## Behavior

- Every Member maps to one basic/inactive Person using only the Member primary key and `members.person_id`.
- Only non-ignored legacy LINE rows with an existing Member FK become linked LINE auth identities.
- Only those reliably linked Members receive active `team_player`; all other Members remain without that qualification.
- Multiple LINE accounts may map to the same Person; duplicate provider subjects and orphan Member links fail closed.
- The checksummed backfill is a non-executable template until rendered from a strict-valid inventory. The rendered SQL
  embeds only approved aggregate counts—not IDs or subjects—and rechecks them before its first write.
- The transaction uses 5-second lock timeout, 60-second statement timeout, a fixed advisory transaction lock and row
  locks. Re-running the same rendered successful batch is idempotent.
- Member, identity and qualification effects receive separate append-only audit rows with deterministic request IDs.
- Inventory and post-check output only fixed six-column booleans/counts/revision; no Member ID, LINE subject, name or
  row value is emitted. Each metric has a fixed status, value type and exact/nonnegative gate.
- Inventory verifies all 13 Phase A tables, 13 RLS-enabled tables, zero forced RLS, zero policies and both append-only
  triggers. Post-check rejects unexpected audit actions/request IDs and mismatched Member/identity/qualification audit
  relationships.

## Verification

- `python -m unittest tests.portal_data.test_phase_b_artifacts -v`: 11/11 passed on local PostgreSQL 16.
- `python -m unittest discover -s tests/portal_data -v`: 119/119 passed on local PostgreSQL 16.
- Full backfill rerun preserved `(people, identities, qualifications, audits, linked members) = (2, 1, 1, 4, 2)`.
- Exact full transaction rendered with final rollback restored the zero-row Phase A fixture state.
- Non-batch Person drift failed closed without adding any further rows.
- Two LINE subjects linked to one Member produced two identities and exactly one qualification.
- A line-user count change after inventory failed before any portal write.
- Every metric was negatively tested for wrong status, wrong value column and failed gate; every zero-required integer
  rejects `1`.
- Unexpected and relationship-inconsistent audit rows made post-check fail closed.
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
