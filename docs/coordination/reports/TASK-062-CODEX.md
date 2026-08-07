# TASK-062 Codex report

## Status and commits

- Status: `ready_for_review`
- Task base recorded by Work: `f138e6e`
- Branch starting HEAD (TASK-061 review/TASK-062 planning): `2ef8182003fb30be86cc32973376be42c85f7484`
- Implementation commit: `0c86f53789a82e19a924575eb90ae00519a7a28b`
- CI-only formatting commit: `1d810077a0d3fcfee9f9994aa2ea6400ef973733`
- Branch: `codex/task062-deterministic-postchecks`
- Draft PR: `#63`

## Delivered behavior

- Added checksum-pinned read-only pre/post-check SQL with one result set and the fixed sanitized
  six-column CSV contract. Both use bounded transaction-local timeouts and `ROLLBACK`.
- Pre-check fails closed unless the ten-table legacy/RLS boundary is intact and the marker,
  `members.person_id`, and all 13 portal tables are absent. It records only per-table aggregate counts
  for later comparison.
- Post-check verifies revision `0003`, exact portal column and constraint fingerprints, the three
  indexes, append-only function/triggers, nullable bigint/unique/FK/empty `members.person_id`, 13 empty
  application tables, 13 enabled/0 forced RLS, zero policies, zero public grants, and legacy counts.
- Added a strict offline validator for repository SQL/sidecars and exported pre/post CSV pairs. It
  rejects checksum drift, malformed headers, missing/duplicate/unknown metrics, wrong statuses/types,
  sensitive-looking values, failed gates, and legacy aggregate drift.
- Added sanitized fake fixtures, mutation tests, clean/partial-state rehearsals, PostgreSQL 15/16
  compatibility evidence, runbook commands, evidence-template fields, and hosted formatting coverage.

## Verification performed

- Repository artifact verifier and fake pre/post validator: passed.
- Full portal-data suite on isolated PostgreSQL 16: 105/105 passed.
- TASK-062 suite on an ephemeral PostgreSQL 15 container: 9/9 passed.
- Mutations covered portal row insertion, legacy row insertion, RLS disable, policy creation, index
  removal, failed pre-gate after migration, malformed CSV/metrics/values and SQL checksum drift.
- `compileall`, isort, Compose config and `git diff --check`: passed.
- Hosted Python 3.10 CI run `31179324060`, job `92868558830`: passed, including Black 24.4.2 and the
  full repository workflow.
- The first CI run failed only Black formatting; the exact formatter version was applied in an
  ephemeral Python 3.10 Linux container and CI then passed.
- TASK-062 containers/networks and temporary formatter venv were removed. The pre-existing fake-data
  Compose volume was retained; no PostgreSQL 15 volume was created.

## Safety confirmation

- No Owner CSV, backup/archive, credential or env file was read.
- No Supabase/production connection, SQL, migration, DDL/DML, stamp, backfill or data access occurred.
- No merged migration artifact, revision, model, runtime service, RLS policy or grant was modified.
- No deployment, notification, Secret, IAM, Scheduler or cloud resource operation occurred.
- Branch push, Draft PR and CI inspection were within the Owner-approved TASK-062 PR work package;
  no merge was performed.

## Remaining gate

- Work must inspect the actual commits/diff and hosted CI before acceptance.
- PR #63 remains Draft and unmerged.
- Passing these checks does not authorize production migration. A future exact execution package must
  still identify the approved merged commit/checksums, fresh pre-check evidence, window and recovery
  boundary, and obtain separate Owner approval.
