# TASK-125: No-disclosure staging credential broker

- Task type: repository implementation followed by separately authorized dogfood
- Delivery group: `mobile-staging-acceptance-automation`
- Requires independent PR: false
- Status: architecture corrected; waiting for TASK-123 integration and durable operation-journal design
- Operator: agent for repository work and approved fictional staging actions
- Owner gate: one-time provider-subject Secret provisioning and any required IAM

## Goal

Allow DEC-098 agent-operated fictional staging inspect, grant, restore, and
reconcile actions through a privilege-separated bounded broker. The agent may
invoke named operations but cannot retrieve the database URL or LINE provider
subject, impersonate the broker identity, deploy different broker code, or
change its target. This removes the recurring Owner private-console copy/paste
gate; it does not automate LINE login/consent or production actions.

## Scope and ownership

The first implementation writer owns the bounded broker service, its direct
tests and deployment contract, and one TASK-125 report. A later serial launcher
writer may add only the broker client after the active TASK-123 correction is
integrated. Reviewers are read-only and split narrowly between credential/IAM
boundaries, server-side operation semantics, and launcher client behavior.

No Flutter, production, notification, release signing, store, or
general-purpose Secret tooling is in scope. A durable non-secret operation
journal may require a separately reviewed staging-compatible schema migration;
its ownership is coordinated with fixture-lifecycle work before either writer
starts. Cloud broker/Secret/IAM creation is not authorized by this repository
task.

## Invariants

- Broker mode is an explicit non-default action mode. Routine `help`,
  `preflight`, `status`, build, install, and lifecycle paths do not initialize
  `gcloud`, resolve Secret references, inspect private environment, or import
  the data mutation operator.
- The broker runs under a dedicated non-production runtime identity that alone
  can access exact numeric enabled Secret versions. The agent identity receives
  only broker invocation; it has no Secret access, broker impersonation,
  deployment/update, service-account actAs, or IAM mutation permission.
- An Owner-approved manifest pins exact broker source/artifact SHA, immutable
  image digest, operator artifact, project, region, service, runtime identity,
  exact numeric Secret resources/versions, and opaque database-target
  fingerprint. `latest`, tags, mutable images, multiple results, and reference
  drift fail closed before operations.
- The broker retrieves both payloads internally and invokes only the fixed
  operator in the same privilege boundary. Raw payloads never cross the broker
  response boundary or enter caller argv/environment, command echo, process
  metadata, evidence, transcript, exception, crash report, trace, or file.
  Child output is never forwarded. Normal paths dispose buffers and terminate
  process trees; the contract does not claim reliable memory zeroization after
  abrupt OS/process failure.
- Broker observability disables payload-bearing tracing, transcripts, command
  history, request/response body logs, debug dumps, and automatic exception
  capture. Logs and responses use only bounded reason codes and opaque
  operation IDs.
- Mutation remains: read-only inspect -> exact typed confirmation or a
  task-owned machine confirmation bound to the inspect fingerprint -> at most
  one mutation -> independent post-check. Unknown/interrupted outcomes perform
  read-only reconcile and never blind retry.
- A durable non-secret journal records `inspected`, `confirmed`,
  `mutation_issued`, `postcheck_complete`, or `reconcile_required`. One opaque
  operation ID binds the exact inspect fingerprint and intended transition.
  Server-side compare-and-set/idempotency prevents duplicate effects across
  caller or broker crashes.
- A normal lock conflict fails before Secret retrieval and mutation. A stale
  lock or journal entry after `mutation_issued` enters broker-internal read-only
  reconcile and can only complete the same operation or return
  `reconcile_required`; it never starts another mutation.
- Provider-subject and database payloads are never accepted from caller
  environment, stdin, config, argv, request body, or persisted approval files.
- Production, login/QR/consent, public/paid IAM, real notifications,
  irreversible deletion, and release signing/store remain Owner-only.

## Acceptance

1. Noninteractive client precheck proves the exact approved broker artifact,
   caller, project, region, service, runtime identity, immutable image and
   numeric enabled Secret metadata, and returns `OWNER_ACTION_REQUIRED` before
   invocation when provisioning or IAM is absent. It never grants the caller
   raw Secret access.
2. With mocked approved references, one broker invocation performs inspect,
   confirmation, at-most-one fictional mutation, and independent post-check;
   interrupted/unknown results reconcile read-only without a second mutation.
3. Adversarial sentinel tests cover broker/client stdout, stderr, response,
   logs, traces, exception, evidence, argv, process metadata, crash/timeout
   handling, and files. No test claims hard-failure memory zeroization.
4. Wrong account/project/service/reference/version, zero or multiple payload
   records, malformed subject/DSN, concurrent/stale lock, child timeout, and
   post-check mismatch all fail closed with stable governed JSON and nonzero
   exit.
5. Routine action tests prove zero `gcloud`, Secret, private-env, and mutation
   operator initialization.
6. Durable-journal tests cover crash before mutation, crash after issue, stale
   lock, concurrent same/different operations, exact idempotent replay, and
   reconcile-required outcomes.
7. A controlled staging dogfood occurs only after repository review/CI and a
   separate Owner approval for exact broker/Secret/runtime/IAM provisioning and
   the approved target manifest.

## Verification budget

- Writer: one affected direct launcher suite plus parser/format/diff/scope.
- Security reviewer: targeted sentinel, process-boundary, and IAM/reference
  tests only.
- Main Work: targeted state-machine and routine/private separation review.
- Hosted CI: one final deployment-tool gate. Infrastructure-only retry on the
  same SHA does not consume another product verification round.
- Dogfood: one precheck, then one exact broker action after Owner provisioning;
  unknown results reconcile read-only and stop.

## Five-line execution checkpoint

1. Goal: remove recurring Owner credential copy/paste without exposing payloads.
2. Files: launcher, direct tests, mobile runbook, one TASK-125 report.
3. Invariants: fixed staging identity, child-env only, no disclosure, one mutation, reconcile unknown.
4. Tests: adversarial process/env matrix, routine isolation, concurrency, exact state machine, hosted tool gate.
5. Blocker: coordinate the durable journal with C; later Owner must approve exact broker artifacts, both Secret versions, runtime identity, invocation IAM, and target manifest.
