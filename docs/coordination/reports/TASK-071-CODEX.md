# TASK-071 Codex report

## Result

Status: `ready_for_review`

Branch: `main`

Base commit: `6c4be4963fc2febe9032cc8fb48fc3f167064b3e`

Implemented a repository-only Phase C production migration readiness package. No production
database, Supabase SQL, deployment, runtime flag, cloud resource, Secret or notification endpoint
was accessed or changed.

## Delivered package

- Added checksummed, read-only production inventory and post-check SQL with the fixed sanitized
  six-column contract. They cover PostgreSQL/session/ownership privilege risk, exact Phase A/B
  fingerprints and RLS boundary, forced-RLS/policy/grant/trigger gates, exact Phase B identity,
  qualification and audit relationships, 0004 collision checks, attendance resolvability and stable
  legacy aggregates. Runtime flags are explicitly marked out-of-band.
- Added `tools.portal_data_phase_c_readiness` with canonical SQL/checksum verification, strict CSV
  validation, sensitive-looking value rejection and inventory/post-check classification as `pass`,
  `safe_retry_after_confirmed_rollback`, ambiguous commit or semantic drift.
- Strengthened the exact 0003-to-0004 migration verifier for BOM/encoding/line-ending drift,
  unresolved placeholders and a single exact Alembic head, while retaining deterministic
  source-to-artifact byte comparison and existing forbidden SQL gates.
- Added an execution/recovery runbook with a 30-minute evidence window, mutation freeze, fresh Owner
  approval, exact one-transaction execution, immediate comparison and explicit pre-commit rollback,
  ambiguous-commit and forward-recovery boundaries. Runtime flags remain off.
- Added Python 3.10/PostgreSQL 16 CI coverage. No application behavior, migration source, grants,
  policies, roles, cleanup or dual-write path changed.

## Verification

- `python -m tools.portal_data_phase_c_migration verify`: passed.
- `python -m tools.portal_data_phase_c_evidence verify`: passed.
- `python -m tools.portal_data_phase_c_readiness verify`: passed.
- `python -m compileall -q migrations tools tests/portal_data`: passed.
- Hosted-CI-equivalent Black check for all 13 listed files: passed.
- `python -m unittest discover -s tests/portal_data -v`: 154/154 passed against the repository
  localhost-only PostgreSQL 16.4 fixture.
- New rehearsal coverage includes clean 0003-to-0004 inventory/post-check comparison, catalog
  fingerprints, complete attendance bridge, exact forced-RLS/audit/policy drift negatives, atomic
  injected mid-migration failure, five-second lock timeout/full retry, graph/checksum/encoding/EOL/
  placeholder/unexpected-SQL rejection and compare outcome classification. Existing tests retain
  unresolved-attendance atomic rollback, fresh install and downgrade/upgrade coverage.
- `git diff --check`: passed before coordination handoff.
- The local Compose container/network was stopped; the fake-data volume was retained.

## Review and safety boundaries

- The local database owner is a fixture superuser/BYPASSRLS role. The inventory reports these as
  explicit `risk` booleans; production results require Work/Owner review and are not inferred from
  local success.
- No production inventory exists yet. Production revision, fingerprints, row counts, locks,
  ownership, grants, backup/PITR readiness and transaction duration remain unverified.
- Runtime/identity-maintenance flags cannot be established safely by database SQL and remain an
  explicit out-of-band execution gate.
- A committed 0004 with failed semantic checks has no destructive automatic rollback. The runbook
  requires feature-off hold and a separately approved forward-recovery task.
- No production migration, push, pull request or deployment was performed in this implementation
  turn.
