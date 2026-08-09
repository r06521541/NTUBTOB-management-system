# TASK-086 Production zero-admin bootstrap recovery

## Goal

Safely execute the previously reviewed zero-admin bootstrap exactly once now that the fixed production read-only diagnostic has proved the earlier uncertain invocation made no database change.

## Base and confirmed state

- Base commit: `72a015c53fea563843edead2ebbb862391638996`.
- The fixed eight-field production diagnostic returned all six guards `pass`, `active_admin=zero`, and `completed_relationship=zero`.
- The earlier launcher therefore did not apply the bootstrap mutation.
- Production Cloud Run metadata uses the exact env envelope already accepted by the diagnostic and unrelated Secret references use `secretKeyRef.{key,name}`.

## Owner authorization

On 2026-08-10 the Owner explicitly approved this recovery and continuous execution through repository correction, review, one ready PR, hosted CI, squash merge, one production bootstrap DML sequence, and read-only verification. This does not authorize schema/DDL, deployment, Secret payload reads, IAM/Scheduler/flag/traffic changes, notifications, ad-hoc repair, or 56-Person activation inside this task.

## Repository scope

1. Replace the production launcher's failing single-element metadata projection with the same fixed in-memory container env metadata parser and cleanup boundary reviewed in PR #94.
2. Keep exact account/project/service/region, runtime, dependency, checksum and merged-commit guards.
3. Require exactly one unique plain `WEB_PORTAL_ADMIN_MEMBER_IDS`; accept only confirmed `{key,name}` Secret reference schema for unrelated entries; never resolve or disclose values.
4. Preserve the exact sequence `discovery -> preflight -> dry-run -> execute -> post-check`, a new internally generated request ID, one transactional domain mutation, redacted fixed output and unconditional cleanup.
5. Add adversarial metadata tests plus isolated PostgreSQL 15/16 success, idempotency, ambiguity, rollback and concurrency evidence. The launcher must not perform any external operation during tests.

## Production execution

After Work acceptance, one ready PR, required hosted CI and squash merge:

1. Run the exact merged launcher once with the exact merged SHA.
2. Do not rerun on uncertain output or connection loss.
3. Run the independently reviewed fixed eight-field read-only diagnostic once after a successful launcher result.
4. Success requires all guards `pass`, `active_admin=one`, and `completed_relationship=one`.

## Stop boundaries

Stop without ad-hoc repair if metadata, private PG, schema, logging, target uniqueness, aggregate, audit, transaction, output or post-check evidence differs from the reviewed contract. Do not begin the 56-Person activation until TASK-086 is conclusively successful.
