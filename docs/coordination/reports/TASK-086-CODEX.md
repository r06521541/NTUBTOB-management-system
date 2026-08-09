# TASK-086 Codex report

## Delivery

- Branch: `codex/phase-c-production-bootstrap`
- Base: `f236f75609e6ede95a5981c2423cdada895f8100`
- Planning head: `004cba1c8feb1911ba70f7b949db343d1e3fdee9`
- Implementation: `74ce7b632a35fed7a105655e025d602fa3b165b1`

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
requires Python 3.10, pinned SQLAlchemy/Alembic/psycopg2 versions, a clean exact
merged commit, checksummed operator/domain/model sources, and the fixed gcloud
account/project/service/region. It consumes only the five approved PG keys from
the fixed private file, requests only the single Web Portal allowlist metadata
projection, keeps both values out of argv/output/errors, and clears the
temporary operator process environment in `finally`. A pre-existing sensitive
process variable is itself a stop condition so gcloud subprocesses cannot
inherit it.

The launcher runs exactly discovery, preflight, dry-run, execute, and the new
read-only post-check. Offline launcher/operator suites passed 19 tests. The
hosted-equivalent full portal-data suite passed 190 tests on each isolated
PostgreSQL 15 and 16 container; both temporary containers were removed.

This correction did not inspect the approved private file, invoke gcloud, or
access production. The actual launcher remains gated on Work review, hosted CI,
squash merge and the exact merged commit.
