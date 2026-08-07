# TASK-062 Codex report

## Status and commits

- Status: `ready_for_review`
- Task base recorded by Work: `f138e6e`
- Branch starting HEAD (TASK-061 review/TASK-062 planning): `2ef8182003fb30be86cc32973376be42c85f7484`
- Implementation commit: `0c86f53789a82e19a924575eb90ae00519a7a28b`
- CI-only formatting commit: `1d810077a0d3fcfee9f9994aa2ea6400ef973733`
- Work-review catalog/access correction: `4d547b8f3117a7a7902cd482e4e3e5818b1af32e`
- Final code HEAD (pre-only execution gate): `355e460e818eaed01a1c4cd7edc38615110c16ba`
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
- Full portal-data suite on isolated PostgreSQL 16: 106/106 passed.
- TASK-062 suite on an ephemeral PostgreSQL 15 container: 10/10 passed.
- Mutations covered portal row insertion, legacy row insertion, RLS disable, policy creation, index
  removal, failed pre-gate after migration, malformed CSV/metrics/values and SQL checksum drift.
- `compileall`, isort, Compose config and `git diff --check`: passed.
- Final-code hosted Python 3.10 CI run `31180936064`, job `92873772129`: passed, including Black
  24.4.2 and the full repository workflow.
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

## Work-review corrections and execution handoff facts

- Pre-check now repeats the approved TASK-061 legacy table, column and PK/FK fingerprints plus the
  generic schema owner, usage/create, legacy relation ownership and grant-count boundary.
- Post-check requires the exact approved legacy fingerprint transition and unchanged legacy access
  counts. It also rejects PUBLIC/non-owner direct portal grants and non-owner table default ACLs;
  owner implicit privileges are not misclassified.
- Local mutation tests prove rejection of legacy column drift, legacy constraint drift, direct grant
  to a non-owner role and default-table grant drift.
- Reviewed SQL checksums:
  - pre-check: `51ce7d88463f96bcf1a9cd12d0c3e1eeb5c17f5f0bdf19d466e7a0e296e6cd33`
  - migration: `81fa1ba1a2d2d856d4b4393cbdfbc663d6c19759f758f36b08e76e39a964636a`
  - post-check: `4ed0c186db2df4c735d8dd93857d060efd48c57d2a05972cc90617c6b3c83546`
- If a later TASK-063 is separately approved, the Owner-facing SQL order is exact:
  1. execute `TASK-062-phase-a-precheck.sql`, export its only CSV outside the repository, and run
     `python -m tools.portal_data_phase_a_evidence validate-pre <absolute-pre.csv>`;
  2. only after that passes, execute `portal-data-0001-to-0003.sql` exactly once;
  3. execute `TASK-062-phase-a-postcheck.sql`, export its only CSV, then run the strict combined
     `validate <absolute-pre.csv> <absolute-post.csv>` command.
- Remaining blockers are a separate Owner-approved TASK-063 execution package, exact merged commit
  and checksums, fresh execution-time pre-check, retained recovery artifact, maintenance/freeze
  confirmation and an unchanged migration-owner boundary. No production execution is authorized.
