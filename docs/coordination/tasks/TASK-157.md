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
- This recovery has not independently verified external provider, Secret/IAM,
  signing, revision or traffic state. Reported preparation is not acceptance
  evidence and must not be repeated as confirmed fact.
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
2. Verify a single active account, then use the private provider-approval
   project and
   explicit region/service flags for every cloud read; do not require or modify
   the local default project/region when DEC-100 resolves a different target.
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

After the artifact verifier and read-only checks confirm exact target, runtime
identity, cost ceiling, public boundary and rollback, DEC-100 authorizes agent
execution of existing fail-closed operators for sandbox build, candidate
deployment, health check, traffic promotion／rollback, OAuth client／callback
metadata, runtime env, existing Secret references, fictional data and bounded
service-account IAM. Owner-reserved actions in DEC-100 remain Gate B.

### Gate E — real-provider smoke

Human login, consent, credential entry or account selection is
`operator=owner`. Agent-owned steps are limited to prepared navigation,
sanitized observation and reversible staging controls. Run one bounded smoke
covering Google sign-in, existing-Person linking, LINE/Google recovery, failure
truthfulness, logout/session invalidation and rollback readiness. Do not expand
the acceptance harness or treat absence of logs as success.

Production promotion is outside TASK-157 and requires a new exact Owner work
package after staging evidence is accepted.

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
- Every mutation, deployment and human provider action has its own exact Owner
  approval and recorded post-check; ambiguous results use read-only recovery
  diagnostics rather than replay.
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
- 2026-08-26: Stage C artifact-authority correction is in progress. No cloud
  or provider mutation is authorized by this correction.
- Next action: complete Stage C, then resume Stage A and stop at Gate B or an
  earlier stop condition.
