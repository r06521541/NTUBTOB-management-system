# TASK-157 Google Auth staging rollout verification

## Classification

- task_type: delivery
- risk: L3 authentication / Secret / deployment boundary
- delivery_group: `google-auth-staging-rollout-v1`
- requires_independent_pr: true
- authority_branch: `codex/task-157-google-auth-staging-readiness`
- repository_authority: `1b7d80a41a24c6fbf2ed693ed7d7b017527bf866`
- owner_authorized: 2026-08-25 for task activation; sandbox operations follow
  DEC-100
- standing_authorization: `DEC-100`
- production_or_real_data: prohibited

This task's initial docs-only PR is the safety/authority exception required
before external authentication work. It does not count as a product-code
delivery and does not authorize provider, cloud, Secret, IAM or deployment
mutation.

## Active coordination claim

- claim_id: `main-work-20260825`
- lease_version: 17
- actor_id: `01a03587-d263-7e92-9965-54816f38b8a3`
- role: `main-work`
- scope: task authority, sanitized reconciliation, Owner-gate preparation,
  risk-based acceptance and handoff
- write: coordination documents only; Main Work must not implement and become
  the sole acceptor of any product-code correction
- report target: this task until a separate writer report or operation evidence
  is required
- stop conditions: dirty-state conflict, unexpected target/account/project,
  network/auth failure, unredactable provider metadata, Secret payload, any
  mutation without an exact Owner gate, production access or ambiguous external
  result

The existing `domain-work:flutter` lane remains active but is not assigned work
by task activation alone. A repository correction must receive a separate,
non-overlapping writer claim and an independent auth/security or Flutter
lifecycle reviewer before implementation.

### Completed Stage C writer claim

- claim_id: `task-157-shared-provider-contract-writer-20260826`
- lease_version: 1
- actor_id: `/root/task157_shared_provider_writer`
- role: `codex-writer`
- scope: shared-provider architecture contract and fail-closed provider preflight
- owned paths: DEC-100 clarification in `docs/coordination/DECISIONS.md`; this
  task; `tools/google_auth_staging_preflight.py` and its focused test;
  Google Auth provider-preflight section in
  `docs/operations/mobile/MOBILE_STAGING.md`
- write: exact owned paths only; commit and push the shared task branch
- report target: Main Work
- stop conditions: base／dirty scope drift, authority contradiction, any need
  for provider／cloud／runtime／Secret action, or inability to preserve existing
  private-path／one-shot／no-disclosure guards
- state: completed and independently accepted; PR #192 merged as
  `bd8137b496dc6745bf6a6654d3437a7081c0020b`

### Active Stage D operator claim

- claim_id: `task-157-staging-rollout-operator-20260826`
- lease_version: 1
- actor_id: `01a03587-d263-7e92-9965-54816f38b8a3`
- role: `task-operator`
- scope: sanitized staging ownership evidence, private provider preflight,
  bounded staging build／candidate／promotion／post-check／rollback and Gate E
  handoff
- write: this task branch and coordination closeout only; repository-external
  private approval／consumption evidence; exact DEC-100 sandbox targets only
- stop conditions: project／revision／digest／identity drift, non-staging Secret
  or data ownership, provider/client mutation, production access, public-IAM
  change, Secret payload, login／MFA／consent, ambiguous response or rollback
  unavailability

## Product outcome

Move the Google sign-in and LINE/Google identity linking/recovery implementation
merged by PR #180 from repository-complete to a truthful staging result. The
task must establish what provider-side preparation actually exists, obtain
exact approval for any required changes, and verify the approved staging
artifact through the real provider without weakening state, nonce, session,
identity or authorization boundaries.

## Current facts and non-facts

- Repository implementation is merged at
  `cd49e2038b1d804b3e3c729c510eb8c34df59efb`; its hosted checks and independent
  Web/Auth/DB Security plus Flutter Auth reviews passed before merge.
- The revoked Main actor reported partial provider-side preparation and no
  deployment, traffic change or real-provider smoke.
- Exact live/read-only correlation now verifies the primary Auth Platform is
  External／Testing with one restricted tester and that its sole Web and Android
  clients match the recorded production-candidate Web and Android debug/staging
  clients. Production Google runtime bindings are absent; staging Secret
  reference project and data-binding ownership remain unknown and are not
  acceptance evidence.
- Raw provider identifiers, client IDs, callback values, Secret names, key
  fingerprints and old session/worktree paths must not enter repository files,
  logs copied into reports or user-facing summaries.

## Artifact authority boundary

TASK-157 uses two non-interchangeable artifact classes:

1. `apps/mobile_staging_broker/artifacts/candidate-approval.json` is the baked,
   deliberately fictional broker build-context fixture. It remains governed by
   its broker deployment contract and is never Google Auth provider target
   authority.
2. The Google Auth provider approval is a repository-external private approval
   consumed only by `python -m tools.google_auth_staging_preflight` from the
   repository root. It is assembled only after sanitized read-only inventory
   and Owner target confirmation, remains outside Git, contains no Secret
   payload, and is short-lived and single-use.

For this task, “artifact-derived provider target” means only the verified
private provider approval in item 2. A direct
`python tools/google_auth_staging_preflight.py ...` import failure is not
provider or cloud evidence and is not the canonical invocation.

## Execution stages and gates

### Stage A — sanitized read-only reconciliation

`operator=agent`, `owner_gate=none`,
`standing_authorization=DEC-100 and TASK-157`,
`report_to=main-work`.

1. Resolve only approved stable target aliases from repository authority and
   existing operator tooling, or use the Owner's latest exact sandbox target
   for read-only reconciliation; do not read `.env.yaml` or Secret payloads.
2. Verify the exact shared pair: provider project `ntubtob-schedule-405614`
   remains External／Testing while runtime and data remain in
   `ntubtob-mobile-staging`. Use explicit targets for every read; do not require
   or modify local defaults.
3. Read only the minimum provider/cloud metadata required to classify each
   expected Web, Android, iOS, callback, Secret-reference/IAM and staging item
   as confirmed, reported-but-unverified, missing, inconsistent or blocked.
4. Produce a sanitized delta. Unknown identity, target drift, authentication or
   network failure stops the stage; do not switch credentials or retry through
   another path.

### Gate B — exact mutation approval

Before a sandbox mutation, Main Work records a bounded execution packet with
exact target, action/count, effect, stop conditions, post-check and rollback.
DEC-100-authorized sandbox operations do not require an additional Owner prompt;
Owner-reserved actions listed by DEC-100 still require exact approval.

### Stage C — repository correction, only if reconciliation requires it

Main Work assigns a unique `codex-writer` with owned paths and report target.
The writer supplies the five-line checkpoint, focused regression first,
affected complete auth/security suites, formatter and diff evidence. Named
Web/Auth/DB Security and, when Flutter changes, the existing Flutter Domain lane
perform independent targeted review. One product-code PR is allowed for this
delivery group; the task-activation safety PR is not reused as that PR.

### Stage D — standing-authorized isolated staging candidate

The accepted provider architecture reuses the exact existing Web
production-candidate identity-link client only as the mobile staging server
audience and the exact existing Android debug/staging client. The Web
production-only callback remains unchanged; the staging Auth Platform remains
frozen and non-authoritative. Auth Platform／client／callback／consent／tester
mutation counts are exactly zero.

This repository correction does not authorize runtime work. Before a private
approval or executable CLI may pass, read-only evidence must prove
`secret_reference_project` is `staging_only` or `absent`, `data_binding` is
`staging_only`, production runtime has no Google identity key／Secret binding,
and staging runtime identity belongs only to `ntubtob-mobile-staging`. Unknown,
production or mixed ownership stops. Any later runtime binding, deploy,
promotion or smoke remains a separate Gate B packet under DEC-100.

#### Active Gate B packet — `task157-stage-d-runtime-20260826`

- repository source: exact clean
  `bd8137b496dc6745bf6a6654d3437a7081c0020b`
- target: `ntubtob-mobile-staging`／`asia-east1`／
  `mobile-api-staging`; provider remains read-only in
  `ntubtob-schedule-405614`
- accepted preconditions: schema v4 provider approval canonical SHA-256
  `bff02d2439605ff718b32052859f2087391a4a42f5611d12e2f3788bba6091d6`
  consumed once; runtime identity／Secret references／data binding are
  `staging_only`; production Google runtime bindings are absent
- baseline: revision `mobile-api-staging-task136b-898b0e` Ready at exact 100%,
  ingress `all`, max instances `1`; it is the rollback target
- authorized actions and counts: one staging Cloud Build from the exact source;
  one no-traffic candidate revision `mobile-api-staging-task157-bd8137b4` using
  the exact built digest and existing staging-only runtime identity／Secret
  references; add exactly one plain `MOBILE_API_GOOGLE_AUDIENCES` value for the
  reused Web server audience; then at most one 100% sandbox traffic promotion
- explicit zero counts: OAuth provider／client／callback／consent／tester,
  Secret version／payload／reference, IAM／public access, database/schema/data,
  production runtime／traffic and real notification mutations
- post-check: build success and exact digest; candidate Ready with exact image,
  identity, max instances, Secret refs and Google audience; baseline stays 100%
  before promotion; after promotion candidate is exact 100%, `/health` is 2xx
  and an unauthenticated protected request proves exact revision `0008`
- rollback: on failed or ambiguous candidate post-check do not promote; after
  promotion failure restore `mobile-api-staging-task136b-898b0e` to exact 100%
  and verify it. Retain image, revision, provider resources and evidence; never
  delete or recreate them automatically.
- Owner-reserved boundary: Google login／account selection／MFA／consent and the
  later bounded real-provider smoke remain Gate E human actions; this packet
  does not authorize production promotion.

#### Gate B execution checkpoint — `staging_database_revision_mismatch`

- Cloud Build `7bcb4b5f-354a-4c15-883f-d20f7e74ed4d` succeeded once and produced
  exact digest
  `sha256:a536d41b880f2abd3ac7fd58f2c01ea4e07e7c49bb3a2d6a71d469c5623dbc76`.
- Candidate `mobile-api-staging-task157-bd8137b4` is Ready; its qualified image
  digest, staging-only runtime identity, existing Secret references, scaling
  and sole added Google audience correlation passed post-check. It received no
  traffic before the one authorized promotion.
- The single promotion produced `/health` 200 but the protected revision gate
  returned 503. The bounded candidate log category was exact revision mismatch,
  with no DSN／Secret／driver detail. The automatic rollback restored
  `mobile-api-staging-task136b-898b0e` to exact 100%; candidate positive traffic
  is zero.
- The deployed staging broker attestation identifies exactly one existing
  repository-external candidate approval matching the staging database identity
  and 0008 target. The next operation is Owner-private input of the staging DB
  URL and fictional tester provider subject to the existing
  `tools.mobile_staging_data` recover／single-transaction upgrade path. Neither
  value may enter chat, Git, argv, logs or an agent-readable artifact.
- No retry, second build, second candidate deployment, provider/client change,
  Secret/IAM/data mutation or production action occurred. Candidate/image and
  evidence are retained; Gate E remains blocked until exact 0008 post-check.

#### Gate B recovery checkpoint — `access_audit_lifecycle_classification`

- Owner-private `--recover` reached the existing read-only fixture classifier
  and stopped before Alembic／seed with exact category
  `access_audit` drift. No database mutation or retry occurred.
- Repository analysis found the forward-revision classifier still treated
  `access_audit` as an immutable one-row seed table, while the accepted
  TASK-119／TASK-126 Officer lifecycle is deliberately append-only and already
  has a stricter full-shape validator in the same tool.
- The bounded correction may admit only a complete recognized lifecycle whose
  audit shapes, tester role/version and timestamps are exact; unknown, mixed,
  missing or additional audit rows remain pre-Alembic stop conditions. The
  complete lifecycle is part of the pre/post semantic fingerprint.
- An already seeded forward revision must not be seeded again after the exact
  fingerprint-preserving upgrade. A clean fixture retains the existing seed
  path. This correction does not authorize staging re-execution by itself.
- Resume requires focused isolated-PostgreSQL acceptance, one independent
  Auth/Security verdict and a fresh single-use Owner-private execution gate.
  The retained candidate/image may be reused; no second build or candidate
  deployment is planned.

#### Gate B recovery checkpoint — `mobile_history_classification`

- After PR #193 merged, the next Owner-private read-only recovery stopped before
  Alembic／seed with `Remote staging fixture contains unknown rows`; database
  mutation count remained zero and the operation was not retried.
- One bounded sanitized read-only matrix then proved revision `0006`, no
  event／activity or identity-review rows, all five mobile runtime-history table
  classes present, and the existing complete ownership validator returned
  `mobile_history_exact=true`. No DSN, Secret, provider subject, row value or
  token/hash value entered output or Git.
- The remaining correction may exclude mobile tables from the generic
  must-be-empty check only for a seeded fixture, then require the existing
  all-rows-owned validator and include every mobile row in the in-memory
  pre/post semantic fingerprint. A clean fixture still requires empty mobile
  tables; cross-principal or partial history remains a pre-Alembic stop.
- Resume again requires isolated PostgreSQL 15／16 acceptance and independent
  Auth/Security review. No further staging read or mutation is authorized by
  the correction itself; the next Owner-private invocation must remain single
  use and occur only after the correction is merged.

#### Gate B recovery checkpoint — `broker_journal_classification`

- After the mobile-history correction merged, the next Owner-private read-only
  recovery stopped before Alembic／seed because the `0006` broker journal was
  nonempty. Database mutation count remained zero and the operation was not
  retried.
- One bounded sanitized read-only matrix proved exactly three broker rows, all
  `postcheck_complete`; notification runtime tables were empty and the prior
  exact mobile-history classification remained true. No operation ID,
  fingerprint, timestamp, DSN, Secret, provider subject or row value entered
  output or Git.
- The bounded correction may preserve a nonempty broker journal only for a
  seeded fixture when every row is terminal and has no reconciliation reason.
  Every column is included in the in-memory pre／post fingerprint. Clean
  fixtures, nonterminal／reconcile rows and any notification runtime row remain
  fail-closed before or within the transactional upgrade.
- Resume again requires focused PostgreSQL acceptance, independent
  Auth／Security review and hosted PostgreSQL 15／16 gates before the same
  single-use Owner-private invocation may run.

### Gate E — real-provider smoke

Human login, consent, credential entry or account selection is
`operator=owner`. Agent-owned steps are limited to prepared navigation,
sanitized observation and reversible staging controls. Run one bounded smoke
covering Google sign-in, existing-Person linking, LINE/Google recovery, failure
truthfulness, logout/session invalidation and rollback readiness. Do not expand
the acceptance harness or treat absence of logs as success.

Production promotion is outside TASK-157 and requires a new exact Owner work
package after staging evidence is accepted.
That package must explicitly review the reused Web production-candidate client
and retire／migrate／review Android debug/staging use before provider publishing.

## Verification budget

- Task activation: YAML structure, active task/claim/reference consistency,
  exact docs scope, `git diff --check`, clean status and hosted quick gate only.
- Read-only reconciliation: machine-readable sanitized metadata, exact command
  and timestamp, zero-mutation declaration and independent comparison against
  repository expectations.
- Repository correction: only affected auth/security and direct consumer
  suites; PostgreSQL matrix only if an otherwise prohibited schema/model change
  is separately authorized.
- Staging: exact artifact/revision, health, traffic, bounded provider smoke,
  post-check and rollback evidence. Do not run emulator or complete acceptance
  orchestration unless a concrete platform defect makes it necessary.

## Acceptance and closeout

- External preparation is independently classified without exposing restricted
  identifiers or Secret payloads.
- Every mutation and deployment has an exact Gate B authority packet and
  recorded post-check; Owner-reserved or human provider actions also have exact
  Owner approval. Ambiguous results use read-only recovery diagnostics rather
  than replay.
- Approved staging Google sign-in, linking and recovery either pass with
  truthful failure/session behavior or close as blocked with a precise,
  non-secret reason and unchanged production.
- Any repository correction is independently reviewed, passes required hosted
  CI and is integrated through the delivery group's single product-code PR.
- Closeout records exact repository SHA, sanitized external-state delta,
  verification, rollback state, remaining production gates and zero
  unauthorized side effects. `PROJECT_STATE.md` and `HANDOFF.yaml` are updated;
  `DECISIONS.md` changes only for a new cross-task Owner decision.

## Status

- 2026-08-25: Owner approved the proposed task direction and sanitized
  read-only reconciliation. Task activation safety PR is in progress.
- 2026-08-25: activation PR merged. Initial Web runtime metadata read confirmed
  a healthy single-traffic service without Google client, redirect or pinned
  Secret-reference metadata. No mutation occurred.
- 2026-08-25: Owner established DEC-099 after the existing staging artifact
  resolved a different project than local defaults. Stage A may resume with
  artifact-derived explicit targets and sanitized output.
- 2026-08-25: Owner expanded and consolidated sandbox authority in DEC-100;
  exact sandbox identifiers may be used in controlled tools, and bounded
  sandbox operations no longer require per-command approval.
- 2026-08-25: Owner identified the current sandbox project, but it does not
  match the broker's checked-in fictional candidate fixture. That fixture is
  not provider target authority. All mutation remains blocked until a verified
  repository-external private provider approval is assembled from sanitized
  inventory and passes the provider preflight.
- 2026-08-25: The read-only Console guide reached a session with no selected
  project and a permission-denied Cloud Run view. This does not establish that
  the Owner target is absent; Owner must complete sign-in/account selection and
  select the exact sandbox project before browser inventory resumes. No
  mutation occurred.
- 2026-08-26: Stage C artifact-authority correction merged. Subsequent exact
  read-only reconciliation selected the primary External／Testing provider with
  exact existing Web and Android client reuse while runtime/data remain isolated
  in `ntubtob-mobile-staging`.
- 2026-08-26: Shared-provider contract correction passed independent
  Auth/Security review and hosted CI, then merged through PR #192 as
  `bd8137b496dc6745bf6a6654d3437a7081c0020b`.
- 2026-08-26: Fresh sanitized inventory proved production Google runtime
  bindings absent and staging runtime identity／Secret-reference／exact-0008
  data binding `staging_only`. The repository-external schema v4 approval was
  consumed once and provider preflight returned `PASS`; no external mutation
  occurred in those stages.
- Next action: execute only the active Gate B packet, preserve the exact
  rollback revision, and stop at Gate E for Owner human login／consent.
