# TASK-112 Codex report

## Result

- Added fail-closed staging contracts that reject the production project,
  require independent approved staging and production database identity hashes,
  validate exact revision/runtime names/Secret references and render a redacted
  manifest without DSN, host, credential, Secret payload or provider subject.
- Added read-only cloud/database preflight helpers. Cloud inventory only lists
  configuration, Cloud Run and Secret metadata names; database inventory uses an
  explicit read-only transaction and rejects revision drift, production-shaped
  People and partial fictional fixture state.
- Added deterministic fictional seed/cleanup primitives with a local-only direct
  CLI for three Basic People,
  future Games and attendance states plus exactly one private tester mapping.
  Provider subject is used only as a bound database parameter, never printed or
  hashed. Seed/retry/cleanup verify exact fixture cardinality and drift.
- Added a dry-run-first deployment operator with exact private approval schema,
  clean full-SHA guard, shared artifact/archive and Docker-context checks,
  no-traffic bounded candidate, separate promotion/rollback and private
  interruption recovery. Candidate post-checks require the approved digest,
  zero traffic, scaling, runtime identity, Secret references and audience;
  promotion/rollback require exact traffic convergence. It contains no project,
  billing, API, database, Secret, service-account, IAM or LINE-channel creation
  command.
- Added the value-free Flutter staging build command and complete Owner approval,
  mutation, rollback and cleanup tabletop. No Flutter source was changed.

## Main Work review correction

- Corrected the Flutter template to the client-owned `APP_FLAVOR`, `CLIENT_MODE`,
  `API_BASE_URL` origin and `LINE_CHANNEL_ID` defines; a static contract test
  proves `integration.dart` appends `/api/v1`. Flutter source remains untouched.
- Split activation into build approval/build-result state and a second candidate
  approval. Candidate never rebuilds; lost build/candidate responses use exact,
  read-only recovery. A fresh shared sdist is built from clean approved HEAD in a
  temporary directory; stale dist input is rejected and temporary/context copies
  are removed in `finally`.
- Added mutually exclusive bootstrap/update modes. Bootstrap has no fictional
  rollback revision; update requires one exact 100% baseline. Candidate,
  promotion and rollback validate authoritative service traffic. Digest checking
  accepts Cloud Run's repository-qualified or bare digest representation.
- Added database provider plus immutable resource identity to the independent
  approval fingerprint and redacted manifest. Runtime/build service accounts are
  separate and project-scoped; deploy is explicit private/no-traffic while IAM
  remains an Owner-controlled future mutation.
- Added dry-run-first remote data plan plus approved migration/seed/post-check and
  read-only interruption recovery. It never blindly retries an ambiguous state;
  this task did not execute it against any remote database.
- Fixture reply-type rows are now preserved when an exact compatible baseline
  exists. A clean baseline receives clearly marked fixture-owned rows, and only
  those rows are removed after dependent fixture cleanup.

## Safety review

- No GCP, external database, LINE, Secret, IAM, notification, deployment or
  production operation was performed. Only isolated local Docker PostgreSQL was
  used with obvious fake credentials and fake provider subject.
- Production GCP project is a hard deny. A database URL alone cannot authorize a
  target: it must match the independently approved staging identity hash and not
  match the separately supplied production identity hash.
- Revision remains exactly 0005. No migration, model, shared behavior, Makefile,
  production operator, Flutter source or global coordination file changed.
- Runtime approval files, recovery state, DSN and provider subject are private
  execution inputs outside Git. Docker context excludes env/private key/JSON/
  approval/state/test artifacts; the shared package copy is removed after use.

## Verification

- Staging operator/data/Flutter static contracts: 11 passed.
- Mobile API full offline suite: 14 passed (with `shared_lib` checkout on
  `PYTHONPATH`, matching the packaged shared-module boundary).
- PostgreSQL 15 and 16: repository legacy baseline upgraded to exact 0005; 4
  seed/cardinality/drift/retry/cleanup tests passed on each. Downgrade from 0005
  to 0004 and re-upgrade to 0005 passed on each.
- A deliberately incorrect local fake-password rerun failed authentication
  before database access; rerunning with the actual isolated-container fake
  credential passed. No external database was contacted.
- `py_compile` passed for all new Python modules/tests. Black 24.4.2 and isort
  checks passed file-by-file. Docker context/static operator contracts and
  `git diff --check` passed.

## Unverified

- No real GCP, staging PostgreSQL, LINE Console, Flutter build, container image
  build, deployment, browser smoke, promotion or rollback was performed. These
  remain future Owner-approved operations using private inputs.

## Handoff

- Branch: `codex/task-112-mobile-staging-readiness`
- Base/task specification: `6ddf8ecf8320deb802f6e123567da6137a8ae19f`
- Accepted upstream main: `2c33b6e48f89f43a34f44784e9c224971b5cca38`
- Latest implementation/correction commit:
  `f44811605bea0bd941d8df7e20255a554a419db4`
- Prior implementation commit: `5698feaf6a83623335e22e7ac641d0af16fb0132`
- Report: `docs/coordination/reports/TASK-112-CODEX.md`
- Status/next actor: `ready_for_review` / Main Work; no PR created.
