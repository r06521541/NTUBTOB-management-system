# TASK-134: No-disclosure staging broker client foundation

- Task type: work package
- Delivery group: `mobile-staging-acceptance-automation`
- Requires independent PR: false
- Status: ready for targeted review
- Operator: agent under DEC-098 for repository work
- Owner gate: broker Secret/IAM/deployment provisioning after repository acceptance

## Goal

Add the bounded client that lets an agent invoke the private TASK-128 staging
broker without receiving the database URL, LINE provider subject, identity
token, or raw broker response. This task establishes the client boundary only;
TASK-129 harness wiring remains a later work package after provisioning.

## Scope and ownership

One writer owns:

- `tools/Invoke-MobileStagingBroker.ps1`;
- one direct mocked test module;
- the mobile staging runbook and one TASK-134 report.

The TASK-128 broker, TASK-129 harness, launcher, Flutter client, schema,
fixtures, cloud resources, IAM, Secrets and production are read-only or out of
scope.

## Invariants

- The caller supplies only `status` or the fixed broker operation vocabulary
  plus one opaque operation ID. No DSN, provider subject, Secret reference,
  identity token, endpoint, person/session ID or arbitrary payload is accepted
  in argv or emitted in output/evidence.
- A strict value-free config binds the exact staging project, region, private
  service, caller identity, runtime identity, immutable image digest and
  approved executable paths. Missing provisioning returns
  `OWNER_ACTION_REQUIRED/BROKER_PROVISIONING` before gcloud or network access.
- Service metadata must prove the exact private singleton revision, image and
  runtime identity before token acquisition. Ambiguous traffic, public IAM,
  mutable image, identity drift or malformed metadata fails closed.
- The identity token exists only in process memory and is cleared in `finally`.
  HTTP uses an in-memory authorization header; token, endpoint and raw response
  never enter argv, stdout/stderr, exception text, evidence or a file.
- One invocation sends at most one operation request. Timeout, interruption or
  unknown result is never retried. The caller must reuse the same opaque ID
  with explicit `reconcile` after read-only diagnosis.
- A task-owned exclusive lock is acquired before gcloud/token/network access.
  Concurrent or stale ownership fails closed and never retrieves credentials.
- Output is exactly one de-identified JSON envelope with a stable
  PASS/OWNER_ACTION_REQUIRED/DRIFT/TIMEOUT/FAILED classification and bounded
  reason code.

## Acceptance

1. Direct tests prove unprovisioned and invalid config stop before gcloud.
2. Metadata tests cover exact private singleton success, public IAM, identity,
   image, traffic and malformed-output drift.
3. Request tests prove one request, explicit reconcile, timeout/unknown no
   retry, bounded response parsing and exact broker vocabulary.
4. Adversarial sentinels prove no token, endpoint, raw response, exception,
   subject, DSN or executable path disclosure on success and failure.
5. Lock tests prove concurrent/stale rejection before token/network access and
   cleanup after handled failure.
6. Parser, affected direct suite, formatting and diff checks pass. No real
   gcloud, broker, Secret, IAM, staging or cloud operation runs.

## Verification budget

- Writer: one affected direct mocked suite plus parser/format/diff.
- Domain reviewer: one targeted no-disclosure, IAM/private-boundary and
  at-most-once review; no full replay.
- Main Work: one integration-shape review.
- Hosted CI: one final relevant gate. Same-SHA infrastructure retries do not
  consume another product-verification round.

## Five-line execution checkpoint

1. Goal: add the no-disclosure private broker client boundary.
2. Files: one PowerShell client, direct tests, runbook, task and report.
3. Invariants: no payload crossing, exact private metadata, one request, reconcile-only unknown.
4. Tests: mocked identity/metadata/token/HTTP, sentinel, lock, parser and diff.
5. Blocker: real provider-subject Secret, IAM and broker deployment remain an Owner gate.
