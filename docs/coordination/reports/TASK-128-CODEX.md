# TASK-128 Codex report — privilege-separated staging broker core

## Result

- Added a private Flask broker with bounded JSON input/output, health/runtime
  import isolation, a nonblocking pre-Secret process gate, exact project-bound
  numeric Secret references, and no arbitrary command, SQL, or payload dispatch.
- Added actual normalized-byte attestation for a baked fictional candidate
  approval, TASK-126 operator source, broker runtime, migration, Dockerfile,
  Docker ignore contract, and requirements. Runtime does not claim image
  self-verification; the static deployment contract pins the image digest.
- Added a PostgreSQL journal with CAS lifecycle states. Only the winner of the
  `confirmed -> mutation_issued` transition may mutate. Resume after issue and
  reconcile are read-only and reuse the original row.
- Added a minimal TASK-126 context-local 0006 seam. Public TASK-126 functions
  retain their exact 0005 gate and bounded outputs; the broker wrappers accept
  only 0006 plus the one journal table and reset their mode after success/error.
- Removed process-lifetime raw Secret caching. The lazy SQLAlchemy engine is the
  only unavoidable DSN lifetime and is created after attestation and the gate.

## Integration dependency and limits

- Required accepted dependency: TASK-130 commit
  `6099fce0cb9ecdbbb69ec7452df5771417540f20`. It is not cherry-picked here.
  Main must combine both packages in one delivery branch/PR; external rollout
  order is compatibility API first, then 0006 migration/broker.
- The exact TASK-130 revision name exceeds Alembic's prior varchar(32), so 0006
  safely widens `ntubtob.alembic_version.version_num` to varchar(64). Downgrade
  removes the journal but retains this lossless widening because Alembic writes
  0005 only after the downgrade body returns.
- No cloud, Secret, staging, IAM, deployment, production, Flutter, or unrelated
  service operation was performed. PostgreSQL 15 was unavailable locally and
  remains hosted-CI evidence. Independent Sol execution was requested but no
  callable Sol capability was available in this session.

## Verification

- Targeted broker/security/CAS/deployment/seam suite: 25 passed, with the two
  PostgreSQL tests initially skipped before the local matrix.
- Offline TASK-126 compatibility plus seam suite: 53 tests, 32 passed and 21
  PostgreSQL-dependent tests deliberately skipped with database URLs cleared.
- Disposable localhost PostgreSQL 16.2: five migration, constraint, CAS,
  downgrade, and TASK-126 inspect/grant/restore/reset compatibility tests passed.
  The stopped disposable cluster was removed after testing.
- Python 3.10 compile and repository-order pinned isort/Black formatting cover
  all changed Python sources; the final canonical Black check passes. Final
  diff/status checks are performed at handoff.

## Handoff

- Branch: `codex/task-128-staging-broker-core-implementation`
- Base/task SHA: `3d48f19ad586826b5395a30588b4908f3f834330`
- Delivery: commit and push this branch; no PR and no external execution.
