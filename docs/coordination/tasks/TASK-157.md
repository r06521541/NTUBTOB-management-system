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

### Completed Stage D operator claim

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
- state: completed; database revision `0008`, candidate exact 100%, health 200
  and unauthenticated protected 401 passed. No rollback was required.

### Completed Gate E recovery writer claim

- claim_id: `task-157-gate-e-recovery-writer-20260826`
- lease_version: 1
- actor_id: `/root/task157_gate_e_recovery_writer`
- role: `codex-writer`
- scope: make the existing two-provider recovery flow reachable from the
  truthful unlinked-Google state and make governed staging history ownership
  accept any exact identity belonging to the same fictional Person
- owned paths: `clients/flutter_app/lib/basic_app.dart`,
  `clients/flutter_app/test/basic_app_test.dart`, `tools/mobile_staging_data.py`,
  `tools/tests/test_mobile_staging_operator.py`
- write: exact owned paths only; self-review, focused tests, commit and push the
  shared task branch
- report target: Main Work
- stop conditions: any automatic link／recovery, weakened two-provider proof,
  cross-Person ownership, production/provider/cloud/Secret action, schema
  change, unrelated dirty path or inability to preserve full-row fingerprints
- state: completed and independently accepted; merged at
  `8c4d95105a474e07c687839a9b521cc310656a4f`

### Completed registered-signer contract writer claim

- claim_id: `task-157-registered-signer-contract-writer-20260826`
- lease_version: 1
- actor_id: `/root/task157_registered_signer_writer`
- role: `codex-writer`
- scope: permit the exact existing Android debug signer already registered for
  staging without copying or relinking its private key
- owned paths: `tools/Invoke-MobileStaging.ps1`,
  `tools/tests/test_mobile_staging_launcher.py`, this task and the DEC-100
  clarification in `docs/coordination/DECISIONS.md`
- write: exact owned paths only; regression first, self-review and focused tests;
  no commit or push before Main Work acceptance
- report target: Main Work
- stop conditions: any OAuth／provider／cloud mutation, private-key copy or link,
  raw identifier／fingerprint／Secret output, arbitrary external signer path,
  signer ambiguity, unrelated dirty path or inability to reject reparse paths
- state: completed and independently accepted by Auth／Security; PR #198 merged
  the registered-signer correction at base
  `b57a405af83113a69d11c1ac5339f29b09695601`

### Completed fictional tester binding recovery writer claim

- claim_id: `task-157-tester-binding-recovery-writer-20260826`
- lease_version: 1
- actor_id: `/root/task157_tester_binding_writer`
- role: `codex-writer`
- scope: add one fail-closed, staging-only operation that can replace only the
  fictional tester's exact LINE provider subject after the completed provider
  flow proves the seeded subject does not match the Owner's fictional tester
- owned paths: `tools/mobile_staging_data.py`,
  `tools/tests/test_mobile_staging_operator.py` and this task
- write: exact owned paths only; regression first, self-review and focused
  tests; no database／provider／cloud execution, commit or push before Main
  acceptance
- report target: Main Work
- stop conditions: production／unknown database identity, raw subject in
  output／Git／argv, subject collision, non-exact fixture identity or history,
  reparse／replay／expired private packet, multi-row or non-subject mutation,
  ambiguous post-check or unrelated dirty path
- state: implementation handoff complete and superseded by the fresh Gate E
  backend correction writer claim below; no further write authority

### Completed Gate E backend correction writer claim

- claim_id: `task-157-gate-e-backend-correction-writer-20260827`
- lease_version: 1
- actor_id: `/root/task157_backend_correction_writer`
- role: `codex-writer`
- scope: reconstruct and validate the existing Gate E backend correction,
  resolve the independent Auth／Data collision-order finding and preserve the
  registered-signer merged-state authority
- owned paths: this task; `shared_lib/shared_module/identity_linking.py`;
  `shared_lib/shared_module/portal_data/mobile_repository.py`;
  `shared_lib/tests/test_identity_linking.py`;
  `tests/portal_data/test_mobile_api_foundation.py`;
  `tools/mobile_staging_data.py` and
  `tools/tests/test_mobile_staging_operator.py`
- write: exact owned paths only; self-review and focused tests; Main Work is the
  formal acceptor and Auth／Data performs the independent targeted re-review
- report target: Main Work
- stop conditions: any production／provider／cloud／runtime／Secret action,
  weakened proof or collision guard, schema change, unrelated dirty path or
  inability to preserve the existing correction
- state: implementation complete and independently accepted by Auth／Data;
  pending hosted evidence before merge or staging deployment

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

#### Gate B recovery checkpoint — `tester_lifecycle_timestamp`

- After the broker-journal correction merged, the next Owner-private read-only
  recovery stopped before Alembic／seed on the fictional tester `people` row;
  database mutation count remained zero and the operation was not retried.
- A complete sanitized semantic matrix checked every remaining fixture class.
  All identity, role／audit, qualification, attendance, legacy, mobile, broker
  and notification gates were exact. The sole difference was the tester
  `updated_at`, and a follow-up boolean check proved it exactly matched the
  final accepted role-lifecycle audit timestamp. No timestamp or row value
  entered output or Git.
- The bounded correction may accept only that exact lifecycle relationship:
  baseline uses the seed anchor; a changed role lifecycle requires tester
  `updated_at` to equal its final audit `created_at`. The original timestamp
  remains part of the full-row pre／post fingerprint. Any unmatched timestamp
  stays a pre-Alembic stop condition.
- Resume requires the same focused／hosted PostgreSQL acceptance and independent
  Auth／Security review before one final single-use Owner-private invocation.

#### Gate E correction checkpoint — `reachable_recovery_and_history_ownership`

- Database revision `0008`, candidate exact 100%, `/health` 200 and the
  unauthenticated protected 401 gate passed without rollback. Provider, client,
  callback, consent and tester mutation counts remain zero.
- Read-only Gate E design found that a truthful unlinked Google login ends in
  `accountUnavailable`, while the existing explicit recovery entry covered
  only the separate pending-identity state. It also found that the governed
  staging history validator accepted only sessions owned by the seeded LINE
  identity and would reject a later same-Person Google session.
- The bounded correction adds only an explicit manual recovery entry for
  `accountUnavailable` without a review credential. The existing two distinct
  provider actions and explicit confirmation remain mandatory.
- Staging history may accept only one complete same-Person Google recovery
  graph: the linked identity, pending／linked audits, closed review thread with
  no messages and all owned mobile rows must be exact and fully fingerprinted.
  Partial, duplicate, cross-Person or unknown rows remain fail closed.
- No login, consent, identity link, provider, schema, cloud, Secret, production
  or additional staging mutation is authorized until this correction passes
  independent Auth／Security review and hosted PostgreSQL 15／16 acceptance.

#### Gate E correction checkpoint — `registered_android_signer_contract`

- Sanitized read-only correlation proved the configured Android OAuth package
  and signing category match the Owner's existing standard debug signer. The
  isolated launcher signer did not match that registered category, and the
  completed provider flow returned a truthful cancellation rather than a
  staging session. No OAuth／provider mutation or third login replay with that
  mismatched artifact is allowed.
- The launcher may use the current OS user's canonical existing `.android`
  directory only when it is explicitly selected in private launcher config,
  every declared path equals its canonical path, no path ancestor or file is a
  reparse point, and its single regular `debug.keystore` has link count one,
  matches the sole configured SHA-256 allowlist entry and signs the produced
  APK. The launcher holds one read-only／read-share-only file handle across the
  Flutter build and revalidates identity, size, last-write metadata and the
  in-memory fingerprint before／after keytool and build. Arbitrary external or
  C-drive paths, aliases, dot-segment paths, hardlinks, reparse paths, drift and
  multiple signers remain fail closed.
- The private key must remain in place: no copy, junction, symbolic link,
  generation, rotation or repository/evidence inclusion is permitted. Raw
  signer SHA-256 remains only in memory for comparison; manifest, launcher JSON
  and ordinary output expose only a match classification. This correction
  authorizes repository contract work only; rebuild／install／login remain later
  Gate E operations after independent Auth／Security acceptance.

#### Gate E correction checkpoint — `fictional_tester_line_binding`

- The accepted Google and LINE provider flows both returned to the staging App,
  but the exact API classification remained `account_unavailable`. The bounded
  diagnosis is a mismatch between the seeded fictional tester's LINE subject
  and the Owner's fictional staging tester account; no provider, production or
  schema change is required.
- Recovery extends the existing mobile staging data adapter, not the broker
  fixture or a new adapter. A read-only prepare step validates the complete
  revision-0008 fixture and exact identity `-112001／line／-112001／linked`, rejects
  any new-subject collision, and writes only old／new SHA-256 values to a
  short-lived repository-external private packet with a nonce and one-shot
  sidecar. Raw subjects remain hidden process input and never enter output,
  Git, argv or logs.
- Inspect remains read-only. Execute locks the exact row, changes only
  `provider_subject` in one transaction, then requires the complete normalized
  fixture／role／runtime fingerprint to be otherwise unchanged before marking
  the packet consumed. Lost-response recovery may classify and consume an
  already-applied exact result but must never replay DML. Prepare also returns
  an idempotent, zero-mutation `already_applied` result when the exact tester row
  already owns the private subject; a subject owned by any other row remains a
  collision. Expired, consumed,
  reparse, collision, drift, unknown-row or production identity states remain
  fail closed.

#### Gate E correction checkpoint — `real_provider_proof_snapshot`

- The exact Google candidate request reached staging with `201`, while the LINE
  proof request returned `500`. Read-only request metadata and executable code
  identify a repository defect: the proof repository read `updated_at` from the
  domain identity shape even though that shape deliberately omits persistence
  timestamps.
- The proof repository must re-read the exact linked ORM row under provider,
  subject, status and Person binding before issuing a version-bound proof.
  Encrypted proof IDs accept nonzero signed PostgreSQL bigint values so the
  negative fictional staging fixture can complete; zero and out-of-range IDs
  remain invalid. Confirmation still locks and revalidates both exact rows,
  providers, Person binding and version hashes before any mutation.

#### Gate E correction checkpoint — `visible_identity_link_expiry`

- Real-provider dogfood proved the candidate endpoint succeeded, but a LINE
  proof submitted after the five-minute candidate window returned a truthful
  `401`; the existing Flutter UI exposed only a generic retry message and did
  not tell the Owner that the short-lived flow had expired.
- Candidate and proof responses remain bounded to the existing maximum
  300-second contract. Flutter now displays that completion window, keeps the
  earlier of the candidate/proof deadlines, and fails locally before provider
  reauthentication or confirmation when the pair is already expired.
- Expiry retires all in-memory credentials and provider presentation state,
  performs no proof／confirm request, and presents an explicit restart action.
  Token lifetime, backend wire schema, provider configuration and staging data
  remain unchanged.

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
- 2026-08-26: Stage D completed at database revision `0008`; the candidate is
  exact 100%, health and protected gates passed, and Gate E recovery behavior
  merged at `8c4d95105a474e07c687839a9b521cc310656a4f`.
- Next action: independently re-review the Gate E backend correction and obtain
  hosted evidence, then rebuild and reinstall one staging APK before a single
  fresh Owner Google login. Do not change OAuth clients or copy the existing
  private key.
