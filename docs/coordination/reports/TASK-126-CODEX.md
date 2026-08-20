# TASK-126 Codex report — relational staging fixture lifecycle

## Result

- Added read-only `--inspect-fixture-lifecycle` and candidate-gated
  `--reset-fixture-lifecycle` actions with bounded `ready_basic`,
  `ready_officer`, and `reset_required` states.
- Replaced fixed Person version 1/2/3 role ownership with a complete alternating
  audit chain. The TASK-119 pair remains legacy generation zero; later
  generations use deterministic prior-version request IDs and generated audit
  identities. No historical audit is updated or deleted.
- Attendance ownership now follows reserved Person/Game relations. Reset accepts
  arbitrary owned row IDs, timestamps and totals, rejects canonical collisions
  or partial/cross-fixture ownership, and reconstructs canonical values without
  timestamp predicates or fixed affected-row counts.
- Reset reclassifies under a serializable transaction, locks the fixture roots,
  restores a valid Officer by appending one audit, and uses relational absence
  plus canonical-value postchecks. An already-ready Basic fixture is a
  zero-change success; unknown or uncertain state requires read-only inspect.
- Preserved the public TASK-118/120 repair actions and TASK-119 Officer state
  names. TASK-121 now accepts any complete active Officer generation rather
  than only version 2.

## Safety evidence

- The operator performs no DML against `access_audit` history or any `mobile_*`
  table. Mobile ownership remains aggregate/FK-based and never reads token,
  assertion, attempt, installation, encrypted payload or hash material.
- PostgreSQL integration snapshots proved every pre-existing audit and every
  mobile-security row remained byte-for-byte unchanged across reset. A forced
  postcheck failure rolled back Person, attendance and the newly attempted
  restore audit together.
- No seed, model, migration, launcher, Flutter, runtime API, global coordination,
  staging, production, cloud or external database action was performed.

## Verification

- Bundled Python offline affected suite:
  `python -m unittest tools.tests.test_mobile_staging_operator -v` — 51 passed,
  21 PostgreSQL-dependent tests skipped without a database URL.
- Disposable localhost PostgreSQL 16.2:
  `python -m unittest tools.tests.test_mobile_staging_operator.EmptyDatabaseBootstrapIntegrationTest -q`
  — 21 passed, including two role generations, dynamic attendance reset,
  append-only audit/mobile preservation, drift rollback and TASK-118/120/121
  compatibility. The cluster was stopped and removed after testing.
- PostgreSQL 15 was not installed and Docker Desktop's service was stopped, so
  PG15 remains hosted CI evidence; no image or dependency was downloaded.
- `py_compile`, isort check and final Git whitespace/status checks are recorded
  at handoff. Bundled Windows Black CLI and formatter API both remained at high
  CPU with no output through their bounded timeouts; hosted Black remains the
  final formatting gate.

## Handoff

- Branch: `codex/task-126-fixture-lifecycle-implementation`
- Base/task SHA: `bf63775dc287215ea92fd0dddd419e06a3b60f9c`
- Delivery: commit and push to the shared task branch; no PR and no runtime
  execution.
