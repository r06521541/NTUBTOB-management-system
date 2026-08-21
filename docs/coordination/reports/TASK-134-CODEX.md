# TASK-134 Codex report - no-disclosure broker client foundation

## Result

- Added a separate PowerShell client for the accepted TASK-128 private broker.
  It accepts only the fixed broker vocabulary and an opaque operation ID; no
  DSN, provider subject, Secret reference, token, endpoint or arbitrary payload
  crosses its caller boundary.
- Added strict value-free configuration and runtime provenance checks for the
  fixed staging project/region/service, active operator, dedicated caller and
  runtime identities, immutable image digest, ready singleton revision,
  private IAM and approved task lock.
- Identity-token acquisition uses a bounded gcloud access-token command followed
  by an in-memory IAM Credentials `generateIdToken` request for the dedicated
  caller. The broker audience never enters process argv. Tokens are passed only
  through in-memory HTTP authorization headers and cleared in `finally`; raw
  external/HTTP output and the service URL are never emitted or persisted.
- The approved gcloud executable is constrained to standard Google Cloud SDK
  roots, an exact configured SHA-256, and non-reparse path components. External
  output and HTTP response bodies are byte-capped before materialization;
  redirects are disabled so one broker invocation cannot create a second wire
  request.
- One invocation sends at most one operation request. Unknown outcomes are
  terminal `BROKER_RESULT_UNKNOWN`; only a later explicit `reconcile` with the
  same opaque ID may establish the result.
- Unprovisioned configuration returns
  `OWNER_ACTION_REQUIRED/BROKER_PROVISIONING` before any external call.

## Verification

- Direct mocked client suite: 23/23 passed at implementation SHA `583bc969`.
  The streamed-response correction then passed its affected transport slice
  3/3 without replaying the unchanged suite. Together these cover strict
  no-payload config,
  unprovisioned short-circuit, exact and drifted service metadata, unconditional
  exact-caller IAM, dedicated caller token exchange, one successful operation
  request, explicit same-ID reconcile, redirect suppression, bounded external
  and HTTP output, timeout/unknown no-retry, executable provenance,
  lock-before-network and exception-safe cleanup, malformed responses and
  adversarial no-disclosure cases.
- Python compile, isort check and PowerShell AST parser passed.
- `git diff --check` passed. The final changed-path/sensitive-source checks are
  repeated at handoff.
- Black 24.4.2 CLI and formatter API both reproduced the documented bundled
  Windows no-output stall on the single new test file and were boundedly
  terminated. Hosted CI retains the final Black evidence; no formatting claim
  is made locally.

## Limits and next gate

- This repository work did not execute gcloud, access a Secret, contact the
  broker, mutate staging, alter IAM, deploy cloud resources or touch an
  emulator.
- TASK-129 harness integration is intentionally deferred until this client and
  one controlled broker dogfood are accepted. Its existing
  `BROKER_PROVISIONING` stop remains unchanged.
- The next external step is Owner-controlled provisioning of the dedicated
  provider-subject Secret, broker runtime/caller identities and minimal IAM,
  followed by the documented TASK-128/TASK-130 rollout. No payload should be
  pasted into an agent/model conversation.
