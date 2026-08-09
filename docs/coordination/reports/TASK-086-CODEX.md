# TASK-086 Codex report

## Delivery

- Branch: `codex/phase-c-production-bootstrap`
- Base: `f236f75609e6ede95a5981c2423cdada895f8100`
- Planning head: `004cba1c8feb1911ba70f7b949db343d1e3fdee9`
- Implementation: `74ce7b632a35fed7a105655e025d602fa3b165b1`
- Work-review correction: `d931d286d6ed497e20d92ba0962d6146ea126ba7`

The existing TASK-085 operator remains local-only. TASK-086 adds a separate
checksummed production boundary that receives the database URL and complete
administrator Member allowlist only from the process environment. Neither is
accepted in argv or emitted in output or ordinary errors.

Discovery, preflight, and dry-run use an explicit read-only transaction with
local timeouts. They require schema revision 0004, the approved logging-safe
predicate, zero active linked allowlisted administrators, exactly one inactive
eligible allowlisted Member/Person, and exactly one pending unlinked LINE
identity with an unignored legacy row and open unredacted review thread. Any
zero/multiple candidate or state drift stops without mutation.

Execute requires a fixed private environment acknowledgement, generates a
fresh opaque UUID request ID internally, and delegates the only mutation to
the existing TASK-085 advisory-lock transaction. Post-check compares exact
global aggregate transitions plus the identity/Member/Person/legacy/thread and
audit relationship. It then runs one same-request retry and requires a zero
delta. Stdout remains a fixed aggregate/classification-only JSON schema.

The runbook distinguishes the local and production artifacts, orders all
review/hosted-CI gates before production use, and records the no-ad-hoc-retry
stop boundary. No TASK-086 production operation has been performed in this
repository stage.

## Verification

- Offline operator suites:
  `python -m unittest tools.tests.test_production_zero_admin_bootstrap
  tools.tests.test_zero_admin_bootstrap_operator -v`: 11 passed.
- Local isolated PostgreSQL 15 (`postgres:15.8-alpine`), hosted-equivalent
  `python -m unittest discover -s tests/portal_data -v`: 189 passed. Temporary
  container `task086-full-pg15` removed.
- Local isolated PostgreSQL 16 (`postgres:16.4-alpine`), the same full
  discovery: 189 passed. Temporary container `task086-full-pg16` removed.
- The PostgreSQL matrix directly covers production-boundary success and
  same-request retry, generated request ID, schema/logging stop gates,
  identity and Member ambiguity with zero mutation, two-session concurrency
  with one winner, and injected audit failure with atomic rollback.
- Python compileall for the new operator and affected tests: passed.
- Black 24.4.2 formatter API: clean; bundled Windows Black CLI was not used.
- `git diff --check`: passed.

## Limits and next gate

This delivery is repository/local evidence only. Work review, the one ready
PR, hosted PostgreSQL 15/16 CI and squash merge remain mandatory before any
production discovery or mutation. No production database, private environment,
Secret, gcloud, deployment, schema, IAM, Scheduler, runtime flag, traffic,
notification, or 56-Person activation operation was performed.

## Work-review corrections

The read-only logging predicate is no longer reused as proof for DML. Execute
performs a second read-only gate immediately before request-ID generation and
accepts only `log_statement=none|ddl`; `mod`, `all`, unavailable and unknown
values stop before the domain transaction. A real PostgreSQL regression sets
the isolated database default to `mod`, proves execute makes no audit change,
and restores the setting in `finally`.

A separate checksummed launcher now owns the exact production sequence. It
requires the existing bundled Python 3.12.13 executable, pinned SQLAlchemy/Alembic/psycopg2 versions, a clean exact
merged commit, checksummed operator/domain/model sources, and the fixed gcloud
account/project/service/region. It consumes only the five approved PG keys from
the fixed private file, requests only the single Web Portal allowlist metadata
projection, keeps both values out of argv/output/errors, and clears the
temporary operator process environment in `finally`. A pre-existing sensitive
process variable is itself a stop condition so gcloud subprocesses cannot
inherit it.

The launcher runs exactly discovery, preflight, dry-run, execute, and the new
read-only post-check. Offline launcher/operator suites passed 20 tests. The
hosted-equivalent full portal-data suite passed 190 tests on each isolated
PostgreSQL 15 and 16 container; both temporary containers were removed.

This correction did not inspect the approved private file, invoke gcloud, or
access production. The actual launcher remains gated on Work review, hosted CI,
squash merge and the exact merged commit.

## Runtime correction

The documented command and launcher now require the verified bundled executable
`C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`
at exact version 3.12.13. The existing pinned SQLAlchemy 2.0.23, Alembic 1.13.1
and psycopg2-binary 2.9.9 dependency checks remain mandatory. Hosted Python 3.10
compatibility remains a separate CI requirement; the unavailable local Windows
Store alias is no longer an operator dependency.

A real subprocess regression invoked the documented artifact from the repository
root with this executable. With a syntactically valid but unapproved fake commit,
it returned only the fixed safe stop message and exited before any gcloud command,
private environment read or production access. This also exposed and corrected
the direct-script repository import boundary. The offline launcher/operator
suites now pass 20 tests; compile, formatter API and diff checks passed.

## Uncertain-outcome recovery check

After PR #90 merged, the single approved production invocation lost its stdout
and exit evidence in orchestration. This repository-only correction therefore
does not infer the database outcome and does not permit the five-stage launcher
to run again.

The new independently checksummed recovery launcher reuses the exact reviewed
runtime, dependency, source checksum, git, account/project/service/region,
private PG parser, allowlist metadata projection, and clean-process guards. Its
only operator call is the literal `post-check` mode. It never sets the execution
acknowledgement and contains no sequence, request-ID generation, lifecycle
repository, or write-transaction path. Temporary process values are cleared in
`finally`, and ordinary failure remains a fixed redacted message.

Offline structural and behavioral tests prove one `post-check` call, no other
mode or mutation boundary, no execution acknowledgement, checksum failure,
fixed errors, and unconditional cleanup. This stage did not invoke gcloud, read
the private environment or Secret values, connect to production, generate a
request ID, or execute DML. One reviewed/merged recovery invocation remains the
next gate.

Verification for this correction:

- `python -m unittest tools.tests.test_production_zero_admin_post_check_launcher
  tools.tests.test_production_zero_admin_launcher
  tools.tests.test_production_zero_admin_bootstrap
  tools.tests.test_zero_admin_bootstrap_operator -v`: 27 passed, including a
  real bundled-runtime subprocess that stops on a fake approved commit before
  external access.
- `python -m compileall -q` for the new launcher and test: passed.
- Black 24.4.2 formatter API check for the new Python files: clean.
- `git diff --check`: passed.

## Owner-approved read-only diagnostic

- Branch: `codex/phase-c-bootstrap-readonly-diagnostic`
- Base: `75cccd878285ed4a13cdf9c62048ab875e5abf1f`
- Implementation: `f04c3a4b5dbb273c11f2ca27ce0d5519d76398c4`

The recovery post-check returned only its intended fixed stop classification,
so this repository stage adds a separate, independently checksummed diagnostic.
It does not import or call either prior launcher, `operator.run`, or the identity
lifecycle repository. It contains no execution acknowledgement, UUID/request
ID, write transaction, DDL, or DML.

The classifier verifies runtime/artifact/git, exact gcloud guards and one-field
projection, and the exact private PG-file contract in order. Its database stage
uses an explicit read-only transaction with local statement, lock, and idle
timeouts. Schema, safe read-logging, active allowlisted administrator count, and
the completed TASK-086 relationship count are reduced to only the Owner-approved
fixed classifications. Every exception becomes a fixed classification; output
cannot contain raw values or exception text, and resources/private local values
are cleared in `finally`.

Repository-only verification:

- `python -m unittest tools.tests.test_production_bootstrap_readonly_diagnostic
  -v`: 11 passed, including checksum mutation, AST mutation-boundary rejection,
  exact gcloud projection, explicit read-only/timeouts, stage failure redaction,
  fixed schema/count classifications, cleanup, and a real bundled-runtime
  subprocess that stops at a fake merged SHA before gcloud/private access.
- No gcloud command, private environment/Secret read, production connection,
  DDL/DML, request-ID generation, second bootstrap, or 56-Person activation was
  performed.

## Cloud Run env metadata fallback

- Branch: `codex/phase-c-bootstrap-env-metadata-fix`
- Base: `5da0961532ad87414a49faafb5dc2299e941db9a`
- Implementation: `d00dead085ed0823fee50f6c9cf69427dc6c754c`

The unavailable repeated-element server projection is replaced with the
Owner-approved fixed machine-readable projection of only
`spec.template.spec.containers[0].env`. Account/project guards still run first.
The parser accepts exactly one container, strict nested schema, and one unique
plain-value `WEB_PORTAL_ADMIN_MEMBER_IDS`; it rejects missing, duplicate, empty,
malformed, secret-backed allowlist entries, additional schema fields, and wrong
container cardinality. It never invokes Secret Manager or resolves a reference.

Metadata subprocess stdout/stderr are captured as mutable byte buffers. The
complete response, parsed tree, allowlist, private PG mapping, database URL, and
engine are cleared or disposed in `finally`. No metadata is forwarded,
serialized, persisted, placed in process env, or included in exception text.
Adversarial tests include unrelated plain values and Secret references and
prove they are absent from stdout, stderr, fixed result/exception data, files,
and subsequent process environment.

Repository-only verification for this correction uses fake metadata only. No
gcloud command, private file/Secret, production connection, mutation, second
bootstrap, or 56-Person activation was performed.

- Updated diagnostic suite: 14 passed.
- Diagnostic plus existing recovery/launcher/operator regressions: 41 passed.
- Compileall for the affected Python files, Black 24.4.2 formatter API, and
  `git diff --check`: passed.

## Cloud Run Secret reference schema correction

- Branch: `codex/phase-c-bootstrap-secret-ref-schema`
- Base: `d82ac7ee728303cae34d57fcca92e6ccf1f5eac6`
- Implementation: `755e49028876aac6e4ad270bdb805b38ceb57449`

The Owner-approved shape-only probe confirmed unrelated Cloud Run Secret
references use the exact `valueFrom.secretKeyRef.{key,name}` schema. The strict
parser now accepts only that shape while the allowlist remains a unique plain
`{name,value}` entry. Tests explicitly reject the obsolete `{secret,version}`
assumption, secret-backed allowlist, mixed value/valueFrom entries, and extra
fields. Existing response cleanup, fixed output, no-disclosure, read-only, and
no-launcher/operator/mutation boundaries are unchanged.

The diagnostic suite passed 14 tests and the combined related regressions
passed 41 tests. Compileall, Black 24.4.2 formatter API, and `git diff --check`
passed. No gcloud, private environment/Secret, production connection, DDL/DML,
second bootstrap, or 56-Person activation was performed.

## Production zero-admin bootstrap recovery

- Branch: `codex/phase-c-bootstrap-recovery`
- Base: `72a015c53fea563843edead2ebbb862391638996`
- Implementation: `41aee61ac9bdf10544e001b4965253bb969b783b`

The production five-stage launcher now uses the reviewed in-memory Cloud Run
container-env parser. It requires the strict one-container envelope and one
unique plain `WEB_PORTAL_ADMIN_MEMBER_IDS`, accepts unrelated Secret references
only as exact nonempty `secretKeyRef.{key,name}`, and rejects missing,
duplicate, empty, malformed, secret-backed, obsolete, or drifted metadata. It
does not resolve Secret payloads. Captured stdout/stderr and the parsed metadata
tree are mutable containers cleared in `finally`; failures expose only the
fixed metadata-boundary error.

The existing exact runtime/git/checksum/account/project/service/region guards,
fresh internal request ID, and `discovery -> preflight -> dry-run -> execute ->
post-check` sequence remain unchanged. Only `execute` receives the fixed
acknowledgement, and the domain mutation remains one transaction.

### Verification

- Related offline launcher/operator suites: 43/43 passed.
- Local isolated `postgres:15.8-alpine`, hosted-equivalent legacy setup,
  Alembic upgrade, and full `tests/portal_data` discovery: 190/190 passed.
- Local isolated `postgres:16.4-alpine`, the same sequence: 190/190 passed.
- The PostgreSQL matrix covers success, same-request idempotency, ambiguity
  rejection, injected atomic rollback, and two-session concurrency.
- Compileall for the changed Python files: passed.
- Black 24.4.2 formatter API: clean; the bundled Windows Black CLI was not used.
- Launcher checksum and `git diff --check`: passed.
- Both task-owned local PostgreSQL containers were stopped after validation.

This was repository/local verification only. No gcloud command, private env,
Secret payload, production connection, DDL/DML, deployment, runtime mutation,
notification, or 56-Person activation was performed. Work review, the single
ready PR, hosted CI, and squash merge remain required before the separately
authorized production execution boundary.

### Windows canonical-checksum correction

- Fix: `2bebcb43494c93d6e1a84e83fe49f4d161175b03`

Work found the checksum initially recorded the working-tree CRLF byte hash,
while the launcher's artifact verifier deliberately canonicalizes CRLF to LF.
The checksum is now regenerated with that exact runtime algorithm. No launcher
code or production behavior changed. The existing
`test_artifacts_and_exact_runtime_contract_are_locked` test executed
`verify_artifacts()` against the documented Windows checkout and passed.

The combined launcher/operator/diagnostic suite passed 43/43 tests. Compileall,
the direct canonical `verify_artifacts()` check, and `git diff --check` passed.
No external command, gcloud, private environment/Secret, production connection,
DDL/DML, deployment, notification, or 56-Person activation was performed.

## Zero-admin candidate-state diagnostic

- Branch: `codex/phase-c-bootstrap-candidate-diagnostic`
- Base: `93cbbe598d3e4031786f83653d54ca9e5a6bd551`
- Implementation: `ab6f1d52d53661ef011e55d2a29387cb9f5ea57d`

Added an independently checksummed, fixed-schema read-only classifier for the
state that stopped the bootstrap. It reuses the reviewed runtime/git, exact
Cloud Run env metadata, private PG, logging, and cleanup boundaries as a
checksum-locked dependency. Its own source imports no launcher, bootstrap
operator, lifecycle repository, UUID/request-ID generator, or mutation path.

After all six guards pass, one explicit read-only transaction with local
statement, lock, and idle timeouts classifies only fixed enums/counts for the
allowlisted Member, corresponding Person, reliable LINE identity relationship,
eligible pending review thread, non-ignored legacy LINE link, active
team-player qualification, and exact actorless bootstrap audit. Output cannot
contain IDs, names, values, metadata, SQL parameters, credentials, or raw
exceptions. Unknown, ambiguous, malformed, or failed states remain fixed
`other`/`fail` classifications.

### Verification

- Candidate diagnostic unit/adversarial suite: 6/6 passed.
- Candidate plus existing read-only diagnostic suites: 20/20 passed.
- Local isolated `postgres:15.8-alpine`: 5/5 relationship-state tests passed.
- Local isolated `postgres:16.4-alpine`: the same 5/5 passed.
- PostgreSQL tests cover inactive/absent/blocked/active Person, no/pending/same
  Person/other Person identity relationships, pending thread, legacy link,
  qualification, exact audit, and allowlist ambiguity.
- Compileall, Black 24.4.2 formatter API, artifact/material checksums,
  structural no-write scan, real safe-stop subprocess, and `git diff --check`:
  passed.
- Both task-owned local PostgreSQL containers were stopped.

This stage was repository/local only. No gcloud command, private env/Secret,
production connection, DDL/DML, bootstrap retry, deployment, cloud mutation,
notification, or 56-Person activation was performed. Production execution
still requires Work acceptance, one ready PR, hosted CI, and squash merge.
