# TASK-084 Codex report

## Stage A repository/local readiness

- Added `tools.phase_c_closeout`: a fail-closed, redacted closeout manifest
  validator. It accepts only schema 0004, aggregate admin/candidate/audit and
  drift classifications, plus an exact all-on/unfrozen three-service runtime
  vector with classified IAM and 100% traffic. It rejects identifiers, unknown
  fields, runtime drift, duplicate request IDs and an absent admin classification.
- Added checksummed, read-only aggregate inventory SQL. It returns six fixed
  sanitized columns and contains no DDL/DML or session-persistent mutation.
- Added a bounded maintenance activation, candidate verification/promotion,
  idempotent retry, forward recovery and post-check runbook. Candidate IDs and
  request IDs remain outside the repository and require the later exact Owner
  package.
- Work-review correction adds strict six-column CSV ingestion, bounded
  before/action/retry/recovery/post audit comparison, and exact aggregate
  `set_ignored` candidate classification. The runbook now fixes the active
  linked allowlisted-admin classification and same-POST retry boundary.
- Second-review correction makes the SQL metric set and parser contract
  identical, derives admin/drift evidence only from the sanitized SQL, and
  validates the two externally supplied request IDs through exact bounded
  `identity_ignored`/`identity_unignored` action counts and restored candidate
  classifications. Route and PostgreSQL domain regressions replay the same POST
  and same request ID without bypassing existing gates.

## Verification

- `python -m unittest tools.tests.test_phase_c_closeout
  tools.tests.test_deploy_phase_c_rollout
  tools.tests.test_deploy_phase_c_transition_controller -v`: 19 passed.
- `python -m unittest discover -s apps/web_portal/tests -v`: 124 passed,
  2 platform skips.
- `python -m compileall -q tools/phase_c_closeout.py
  tools/tests/test_phase_c_closeout.py`: passed.
- Black 24.4.2 formatter API applied to the new Python files; `git diff --check` passed.
- `python -m unittest discover -s apps/web_portal/tests -p
  test_admin_security.py -v`: 63 passed.
- `python -m unittest tests.portal_data.test_phase_c_lifecycle -v`: 3 static
  tests passed; 9 isolated-PostgreSQL tests skipped locally because no test DB
  URL was configured. The same-request-ID domain assertion is in that hosted
  PostgreSQL path.

## Not performed / remaining boundary

No environment file, Secret, gcloud, production database/inventory, build,
deployment, runtime flag, traffic, Scheduler, IAM, notification or production
identity action was performed. Stage B still needs a separately approved fresh
read-only evidence package; Stage C/D still need Owner approval of an exact
candidate revision, rollback revision, safe candidate classification and two
opaque request IDs.
