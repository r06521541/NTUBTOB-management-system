# TASK-202: Privacy identity and retention decision package

Type: planning; delivery_group: mobile-privacy-policy; risk: documentation only.
Base/head: 2b8e93e9029ac9be924967696b9be544f377c456.
Branch: codex/task-202-privacy-retention-plan.
Status: planning (Owner selected Apple first-login plus complete account deletion).
No standalone documentation PR or hosted build.

## Authority and scope

2026-09-17 latest Owner decision supersedes the earlier applicability-choice gate:
Apple may be the first login provider. Create only a pending service identity until
existing-account proof or administrator pairing/approval; no automatic team access,
email/name merge, or requirement to possess LINE first. Implement genuine in-app
deletion for pending and established accounts; unlink is not account deletion.
Main lease4 replaces completed lease3 for recording this decision and preparing the
coupled implementation boundary. Its owned documentation paths additionally include
`docs/coordination/DECISIONS.md` and `docs/planning/APPLE_ONBOARDING_DELIVERY.md`.
Earlier no-implementation wording described the audit, not a veto of this latest
product approval. Actual source work must establish its L3 packet and review first.
No new Owner choice is needed for these product rules. Retention periods, independently
retained identifiable roster scope, exact deployment and real erasure remain separate.

Owner confirmed on 2026-09-17: individual operator 陳柏安, public support/privacy
contact yces3108@gmail.com, first-party team-operation purposes without advertising
or data sale; then requested execution. These are approved draft inputs, not a
published policy, vendor behavior evidence or retention/deletion approval.
Preserve the six pre-existing Main-owned TASK201 closeout/draft modifications.
Owner subsequently requested a more detailed Apple-aligned design minimizing
changes to existing operations/defaults. Proposal A periods remain unapproved.
Extend this planning task, not a new implementation or live deletion authority.

Main packet: task=TASK-202; branch as above; base/head as above;
actor_id=/root; role=main-work; claim_id=task-202-main-20260917; lease_version=3;
scope=audit actual account-creation/linking paths and candidate evidence; draft truthful Apple questions;
owned_paths=docs/releases/MOBILE_PRIVACY_DRAFT.md,
 docs/planning/ACCOUNT_DELETION_DESIGN.md,
 docs/planning/ACCOUNT_CREATION_APPLICABILITY.md,
 docs/coordination/tasks/TASK-202.md,docs/coordination/HANDOFF.yaml,
 docs/coordination/PROJECT_STATE.md;
write=allowed; report_to=/root;
stop_conditions=policy choice, real data/credentials, deployment, publishing,
store action, irreversible deletion or source implementation outside this task.
Lease1 planning delivered; lease2 replaces it for this bounded Owner request.
Lease2 design delivered. Owner now requests Main choose a thorough bounded audit
and proceed; lease3 replaces lease2. No further Owner decision needed for source
inspection, existing sanitized evidence and public Apple rules. Do not change
product behavior, collect private input, create test users on live services,
send Apple inquiries or claim deletion exemption. No implementation authorization
is inferred from approval of the design or request to investigate applicability.

## Applicability evidence review packet

task=TASK-202; branch=codex/task-202-privacy-retention-plan;
base=head=2b8e93e9029ac9be924967696b9be544f377c456;
actor_id=/root/privacy_foundation; role=advisor;
claim_id=task-202-account-applicability; lease_version=1;
scope=independently trace current source unknown-user/pending/self-link paths and
 distinguish identity creation from Person creation; challenge any login-only claim;
owned_paths=none; write=read-only; report_to=/root;
stop_conditions=private inputs, live data/network mutation, implementation or missing authority.
Prior review claim released. Immediate received/executing with exact identity,
claim/lease/report_to; heartbeat10–15min; blocker immediately; proactive completion
with full HEAD/dirty paths/checks/findings/limits/external mutations to Main.
No application suite or old TASK201 work; Main independently checks build2/current
source deltas and writes the bounded audit while awaiting completion.

## Design checkpoint

1. Outcome: Apple-aligned deletion without changing normal multi-provider/team flows.
2. Paths: planning/privacy/state documents; source read-only, no runtime changes.
3. Invariants: unlink is not deletion; Person key is not personal-data exemption;
   no automatic roster erasure, enrollment, role restoration or account resurrection.
4. Evidence: official Apple rules, exact source relationships/callers, local docs
   checks and independent read-only design review before declaring draft ready.
5. Stops: retained identifiable roster requires evidence/Owner choice; no legal or
   App Review guarantee, final periods, schema work, secrets or external writes.

## Independent design review packet

task=TASK-202; branch=codex/task-202-privacy-retention-plan;
base=head=2b8e93e9029ac9be924967696b9be544f377c456;
actor_id=/root/privacy_foundation; role=advisor;
claim_id=task-202-deletion-design-review; lease_version=1;
scope=challenge frozen ACCOUNT_DELETION_DESIGN.md for Apple requirements, minimal
 impact, false roster/tombstone exemptions, session/legacy bypass, partial failure
 and realistic fulfillment; design review only, not acceptance of own prior draft;
owned_paths=none; write=read-only; report_to=/root;
stop_conditions=private inputs/data, implementation, external mutation, missing claim.
Previous TASK201 advisor claim is released. Follow COLLABORATION section2:
immediate received/executing with exact actor/claim/lease/report_to; heartbeat
10–15min or blocker immediately; proactively send Main final verdict/full HEAD/
dirty paths/checks/findings/limits/external mutations. No source/Git writes or
application tests needed for this document-only review. Main remains active.

Lease1 REQUEST_CHANGES received/handled: R1 missing-token deletion fallback and
separate provider status; R2 intent/generation binding and standalone unlink
release gate; nonblocking backup suppression horizon clarification. Main accepts
all points and corrects the same draft. Lease1 released; same actor/claim now
lease_version=2 for one read-only correction check, same branch/base/head/scope/
protocol/stops. No extra implementation or application suite is authorized.

## Acceptance

- Separate approved operator/purpose from proposed periods and unknown runtime.
- Explain request vs fulfillment, expiry vs erasure, pseudonymization vs anonymity,
  backup recovery, shared history, provider revocation and restricted-account access.
- Give one recommended bounded policy package with explicit clocks and exceptions;
  do not call proposed numbers legal requirements or deployed guarantees.
- Check document links, diff and state consistency; no product change means no
  full application suite or signing/CI cycle. Leave one concrete Owner decision.

## Evidence and result

Confirmed inputs recorded; draft section7 gives proposal A, explicit clocks,
exceptions, source gaps and next engineering sequence. Owner must decide the
periods and identifiable team-history scope before implementation. No formal
implementation acceptance is claimed; the initial period proposal had no delegation.
Owner-requested detailed design subsequently uses the independent packet above.

Inspected account_deletion service/repository, model FK/status constraints,
MobileRepository expiry records, identity_lifecycle redact_closed_reviews,
mobile bootstrap/README and Flutter fake injection/crash queue. Important finding:
review body redaction already uses365days after closure, but caller search found
tests only; no scheduler/runtime execution was proven. Deletion receipts only
allow requested and sessions/identity/person links restrict physical deletion.
Apple official deletion guidance rechecked2026-09-17; proposed periods are not
Apple requirements. No legal-compliance or runtime verification claim.

`py -3.10 -m unittest discover -s tools/tests -p "test_ci_*.py" -q`:
41 total,40 passed,1 skipped. `git diff --check`: passed. No application suite
rerun because only Markdown/YAML planning content changed. No commit/push/PR,
cloud/provider/store/signing/data mutation. Local branch creation only.
Existing TASK201 report/review/task modifications were preserved untouched;
its HANDOFF/PROJECT_STATE/privacy draft updates were extended, not discarded.

## Detailed design delta

`docs/planning/ACCOUNT_DELETION_DESIGN.md` separates unlink/full-account deletion/
team membership, limits erasure to the requesting account, rejects automatic
roster exemptions and describes minimal lifecycle/legacy guards, UI, provider
failure/recovery, backups, re-enrollment and staged rollout. No general retention
scheduler or destructive implementation is authorized by this draft.
Updated privacy draft links the design and keeps proposal A periods unapproved.
Quick contract tests rerun for this doc-only pass:40PASS/1SKIP. Independent
lease2 design ACCEPT was proactively received and handled by Main; R1/R2 closed.
Frozen design LF SHA256 (tools.artifact_digest --text):
`03cc70f83028d1fe75cd5e53d751ebc99c765d1a3d67a80400ae4be2fcacf5a5`.
Reviewer bound the current full HEAD above, reran diff check, made no writes;
no application suite or runtime test. Claim lease2 completed/released, Main
acknowledged accepted; no unattended delegation. Main checked38 local links,
zero missing; PROJECT_STATE155lines before final status wording, under200.
Owner next decides two-entry/service scope and identifiable-roster exception
strategy; proposal A periods still not approved. This is design acceptance only.

## Applicability audit delta — 2026-09-17

Delivered `docs/planning/ACCOUNT_CREATION_APPLICABILITY.md`, including source flow
matrix, recorded build2 comparison, runtime unknowns and UNSENT Apple clarification.
Ordinary exchange does not create Person; linking requires existing linked active
proof. Pending candidate records and conditional LINE non-member new-Person
approval mean a blanket login-only claim is not supported. Provider-generic pending
review does not establish provider-generic admin approval. No Apple exemption claimed.

Advisor task-202-account-applicability lease1 proactively delivered full completion
and limits; Main received, incorporated and acknowledged it, then released claim.
Checks: source tracing and diff check, no application suite or real account creation.
Main compared build2 exact SHA from TASK198 with current source, not deployed backend.
Prior design remains frozen and conditional; its earlier digest is unchanged.
Next optional Owner gate is exact candidate/runtime verification or sending a revised
Apple question after verification, not credential re-entry or unapproved feature removal.
Main lease3 delivered; no Git commit/push/PR or external mutation in this audit.
