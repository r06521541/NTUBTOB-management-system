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
- Third-review correction replaces the known-failing TASK-068 post-audit step
  with one executable five-snapshot closeout contract. The SQL retains its
  non-audit Member/Person, identity-link, duplicate-link and team-player drift
  gates; only the exact Owner-approved ignore/unignore audit pair may be new.
  A sanitized same-target join count proves both actions reference one
  `auth_identity_id`, while candidate aggregates must change exactly `-1/+1`,
  remain unchanged on retry, and fully recover. The runbook now treats psql
  variable substitution as server-bound statement content and requires a
  no-sensitive-input statement-logging/provider preflight before parameters.
- Fourth-review correction requires the complete runtime evidence of all five
  snapshots to equal `before`, including revisions, traffic, IAM, Phase C,
  freeze and maintenance. It also carries five invariant aggregates through
  SQL ingestion and every snapshot comparison: People, Members, identities,
  reliable linked LINE identities, active team players and attendance replies.
  The inventory explicitly excludes deprecated `line_notify_tokens`; the
  runbook records that `set_ignored()` has no notification caller and reserves
  Stage D notification validation for approved production error/log
  classification only.
- Stage B security prerequisite replaces the three controlled SQL inputs with
  PostgreSQL 16 extended-protocol placeholders `$1/$2/$3`. The checksummed
  artifact has one exact-order psql `\bind … \g` execution boundary, preserves
  the read-only transaction, local timeouts and rollback, and rejects SQL-side
  colon interpolation, literal request IDs, or a wrong bind order/count. The
  runbook requires an isolated Docker PostgreSQL 16 client check, `-X -n`
  interactive psql flow, preflight before prompts, and a separate provider
  parameter-payload logging stop condition.
- Docker operator-command correction pins both the PostgreSQL 16 version
  preflight and interactive client to the TASK-056 image ID with `--pull never`.
  The interactive command receives its already-provisioned private env-file
  without reading it, applies `PGOPTIONS=-c default_transaction_read_only=on`,
  and mounts only the exact repository root read-only at `/workspace` before
  loading the checksummed SQL. It contains no DSN or connection identity/value
  in argv.

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
- Third-review targeted rerun: `python -m unittest
  tools.tests.test_phase_c_closeout tools.tests.test_deploy_phase_c_rollout
  tools.tests.test_deploy_phase_c_transition_controller -v`: 22 passed;
  compileall, Black 24.4.2 formatter API comparison, checksum verification,
  and `git diff --check` passed.
- Fourth-review targeted rerun: `python -m unittest
  tools.tests.test_phase_c_closeout tools.tests.test_deploy_phase_c_rollout
  tools.tests.test_deploy_phase_c_transition_controller -v`: 23 passed;
  compileall, Black 24.4.2 formatter API comparison, checksum verification,
  and `git diff --check` passed.
- Stage B prerequisite targeted rerun: `python -m unittest
  tools.tests.test_phase_c_closeout tools.tests.test_deploy_phase_c_rollout
  tools.tests.test_deploy_phase_c_transition_controller -v`: 23 passed;
  compileall, Black 24.4.2 formatter API comparison, checksum verification,
  and `git diff --check` passed.
- Docker command correction targeted rerun: `python -m unittest
  tools.tests.test_phase_c_closeout tools.tests.test_deploy_phase_c_rollout
  tools.tests.test_deploy_phase_c_transition_controller -v`: 24 passed;
  compileall, Black 24.4.2 formatter API comparison, and `git diff --check`
  passed. The local `python` command was unavailable, so the repository's
  bundled Python runtime was used.

## Not performed / remaining boundary

No environment file, Secret, gcloud, production database/inventory, build,
deployment, runtime flag, traffic, Scheduler, IAM, notification or production
identity action was performed. Stage B still needs a separately approved fresh
read-only evidence package; Stage C/D still need Owner approval of an exact
candidate revision, rollback revision, safe candidate classification and two
opaque request IDs.
