# TASK-085 Codex report

## Delivery

- Branch: `codex/phase-c-zero-admin-bootstrap`
- Base: `f09c13eadc1d88c49aaf83a3362ab2a563ad8e7a`
- Original implementation: `77894b8a8e1d6e33f93e8e72288afb99c126bd16`
- First corrections: `7a3f202c3fc15978fcc4b25571bbdd5f7af834fb` and
  `b5234e45b055cfcd48a10edd2da302ee1bfca434`
- Second-review implementation: `428d2099aae576bff73e3814b9ef68df581acfce`

## Hosted CI isolation correction

The PostgreSQL 15/16 hosted jobs exposed an order-dependent fixture leak: Phase C
bootstrap tests may leave newer audit actions such as `identity_pending`, while
the later readiness fixture downgraded directly from 0004 to 0003. Recreating
the older `ck_access_audit_action` constraint then correctly rejected those
rows. The readiness fixture now upgrades to head, truncates only the test
database's `access_audit` fixture rows, and only then downgrades to 0003. No
migration or constraint behavior changed.

`test_readiness_reset_accepts_bootstrap_suite_audit_residue` explicitly leaves
an incompatible Phase C audit row and proves the shared reset reaches 0003 with
an empty audit fixture, preventing the bootstrap-suite-to-readiness ordering
regression.

The repository now has a fail-closed zero-admin Member bootstrap that takes the
existing admin advisory lock, requires zero active linked allowlisted admins,
reuses the normal Member-link transaction and records one existing
`identity_linked` null-actor audit. Retry validation requires the exact target,
before/after state, Member, null actor and bootstrap-prefixed reason.

The checksummed executable `tools/portal_data_zero_admin_bootstrap.py` accepts
only `--mode preflight|dry-run|execute` in argv. The full allowlist, identity,
Member, reason, request ID and execute acknowledgement are interactive
echo-disabled inputs. Output is a fixed aggregate-only JSON schema. The local
operator path checks the target before mutation, requires the fixed execution
acknowledgement and performs an exact aggregate/audit post-check.

The exact checksummed TASK-084 inventory owns `\pset pager off`, bound
parameters, the fixed metric set and `ROLLBACK`; its verifier and true psql16
regression cover that reviewed artifact rather than a generic query.

Direct PostgreSQL tests cover blocked/disabled Person, ignored legacy row,
closed/redacted thread, revoked qualification, wrong identity/Member, ordinary
approval audit retry rejection, two-session concurrency and an injected audit
failure with complete transaction rollback.

## Actual local verification

- PostgreSQL 15: `postgres:15.8-alpine`, local image ID
  `sha256:0b42deb40e1694f2595be402b1c3d9f0ab132aef0912f0904d1f3efc94edc9e1`,
  temporary container `task085-review2-pg15`. The selected six-test
  failure/concurrency/operator dry-run+execute matrix ran with
  `python -m unittest ... -v`: `Ran 6 tests ... OK`. Container removed.
- PostgreSQL 16: `postgres:16.4-alpine`, pinned image ID
  `sha256:89ec47deeeddac28eb60b5672a456c54213ff4528f8752fda7f7c2a0e4ead36a`,
  temporary container `task085-review2-pg16`. The same selected matrix result:
  `Ran 6 tests ... OK`. Container removed.
- `RUN_PSQL16_BIND_INTEGRATION=1 python -m unittest tools.tests.test_phase_c_closeout.CloseoutEvidenceTests.test_psql16_bind_uses_unquoted_variable_payloads -v`:
  passed. The test executed the exact checksummed TASK-084 inventory, its three
  binds, fixed metric set, artifact-owned pager-off and `ROLLBACK`, then reached
  `rollback-complete`; the task container was removed.
- `python -m unittest tools.tests.test_zero_admin_bootstrap_operator tools.tests.test_phase_c_closeout tests.portal_data.test_phase_c_lifecycle.PhaseCArtifactTests -v`:
  18 passed; the opt-in Docker test skipped in this non-opt-in invocation and
  passed in the separately recorded opt-in invocation.
- `python -m compileall` for all changed Python modules/tests: passed.
- Black 24.4.2 formatter API: clean. The bundled Windows multi-file Black CLI
  was not used, per `AGENTS.md`.
- `git diff --check`: passed.
- Hosted-equivalent full discovery on local `postgres:15.8-alpine`, temporary
  container `task085-ci-pg15`: `python -m unittest discover -s
  tests/portal_data -v` ran 183 tests and passed. Container removed.
- Hosted-equivalent full discovery on local `postgres:16.4-alpine`, temporary
  container `task085-ci-pg16`: the same command ran 183 tests and passed.
  Container removed.
- `python -m compileall -q tests/portal_data/test_phase_c_readiness.py`: passed.
- Black 24.4.2 formatter API for the changed readiness test: no changes needed.

No production database, private environment, Secret, gcloud, deployment,
runtime flag, traffic, IAM, Scheduler, notification or 56-Person activation
operation was performed.
