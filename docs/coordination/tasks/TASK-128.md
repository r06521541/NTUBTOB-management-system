# TASK-128: Privilege-separated staging broker core

- Task type: repository implementation
- Delivery group: `mobile-staging-acceptance-automation`
- Requires independent PR: false
- Status: assigned for implementation
- Operator: agent under DEC-098 for repository work
- Owner gate: none until separately authorized cloud/Secret/IAM provisioning

## Goal

Implement the server-side core of the no-disclosure staging broker so an
unprivileged caller can request one bounded fictional fixture operation without
receiving the database URL or LINE provider subject. Persist a non-secret
operation journal that makes interruption and reconciliation explicit.

## Scope and ownership

One writer owns:

- one Alembic revision after `0005_mobile_auth_api_foundation` for the broker
  operation journal;
- a new `apps/mobile_staging_broker/` service core and direct tests;
- narrowly required operator integration tests;
- the mobile staging runbook and one TASK-128 report.

Launcher/client integration, Flutter, fixture seed, existing mobile API, cloud
deployment, IAM, Secret creation/versioning, production and global coordination
are out of scope. Existing TASK-126 lifecycle code is a read-only dependency
unless a minimal broker-safe API seam is required and directly tested.

## Invariants

- The public request vocabulary is a fixed enum of inspect, reset, grant,
  restore and reconcile operations plus one opaque operation ID. No caller
  request, argv, environment, file or response accepts or returns a DSN,
  provider subject, Secret reference, person/session ID or credential-derived
  value.
- The service retrieves the two exact numeric Secret versions only inside the
  privileged process through injected interfaces. Tests use sentinels and prove
  payloads never enter response, logs, exceptions, traces or journal columns.
- A process-local nonblocking operation gate rejects concurrent work before
  Secret retrieval. The deployment contract requires one instance, one worker
  and request concurrency one; durable correctness never relies solely on this
  gate.
- The journal stores only opaque operation ID, bounded operation/target state,
  an opaque inspect fingerprint, lifecycle state, timestamps and bounded reason
  code. It contains no payload, subject, DSN component, Secret metadata or
  identity/session value.
- State progression is append-safe/compare-and-set:
  `inspected -> confirmed -> mutation_issued -> postcheck_complete`, or
  `reconcile_required`. The same operation ID and intent are idempotent; a
  different intent or malformed/unknown state fails closed.
- Mutation is read-only inspect, exact machine confirmation bound to the inspect
  fingerprint, at most one TASK-126 operation, then independent postcheck.
  Crash/timeout/unknown after `mutation_issued` performs read-only reconcile and
  never issues a second mutation.
- The broker pins candidate approval, project, region, service, runtime identity,
  immutable broker/operator artifacts, numeric Secret versions and opaque DB
  fingerprint through a validated non-secret manifest. Mutable/latest or
  ambiguous configuration fails before Secret retrieval.
- Health is public-state only and never initializes Secret or mutation code.
  Operation endpoints assume Cloud Run IAM authentication; application code
  does not add a bypass token or weaken IAM.
- No production target, notification, irreversible deletion, arbitrary SQL,
  arbitrary command execution or general Secret access exists.

## Acceptance

1. Migration creates the bounded journal with exact CHECK/UNIQUE constraints,
   indexes and safe downgrade; PostgreSQL 15/16 prove migration and CAS behavior.
2. Direct service tests cover health/routine isolation, manifest validation,
   zero/multiple/malformed Secret payload records, exact operation vocabulary,
   concurrent lock before Secret access and stable governed JSON.
3. State-machine tests cover success, exact idempotent replay, conflicting replay,
   crash before mutation, crash after issue, stale journal, postcheck mismatch and
   reconcile-required without a second mutation.
4. Adversarial sentinels prove no disclosure through stdout/stderr, response,
   structured logs, exception, journal, request echo, trace or temporary file.
5. Deployment artifacts statically require private invocation, fixed max instance
   one/concurrency one, dedicated runtime identity, immutable image input and
   exact numeric Secret resource versions; no deployment is executed.
6. TASK-126 inspect/reset/grant/restore behavior remains compatible and no
   security/session/audit history is deleted.

## Verification budget

- Writer: one affected broker/operator suite and one PostgreSQL 15/16 migration
  and journal matrix.
- Security reviewer: targeted no-disclosure, privilege/config and crash-state
  review only.
- Main Work: targeted CAS, at-most-once and TASK-126 compatibility review.
- Hosted CI: one final relevant gate. Same-SHA infrastructure retry is not a new
  product verification round.

## Five-line execution checkpoint

1. Goal: implement a no-disclosure broker core with durable at-most-once reconciliation.
2. Files: one migration, new broker service/tests, narrow operator tests, runbook/report.
3. Invariants: no payload boundary crossing, fixed manifest, CAS journal, no blind retry.
4. Tests: direct adversarial suite plus PostgreSQL 15/16 migration/state matrix.
5. Blocker: schema ambiguity or inability to guarantee no-disclosure/at-most-once returns to Main; cloud provisioning remains Owner-only later.
