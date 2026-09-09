# TASK-190: reviewed profile verification intake

- Type: delivery; architecture accepted below; delivery_group task-190-profile-intake; L3.
- Branch: codex/task-190-profile-intake.
- Base/head: 58d90054b52f9c7f5a4788625bd3964ea358c214.
- TASK189 PR244 merged with full CI34391274475 SUCCESS and macOS CMS native rehearsal PASS.
  Prior claims complete; no live assets verified.
- Main /root, main-work, task-190-main-20260910 lease1, owns this task/HANDOFF and
  later explicitly accepted integration paths; no live mutation authority.
- Advisor /root/task181_review, advisor, task-190-security-20260910 lease1,
  read-only, owned_paths none, report_to /root. Mandatory COLLABORATION section2 packet.

## Checkpoint and proposed next boundary

Goal: connect trusted CMS core to a usable private profile verification path, then stop
at the genuine exact Owner custody/execution gate, not another decoder-only deliverable.
Core: future manual-only protected GitHub Environment workflow and bounded local intake.
Invariants: no real file read/Secret configuration/workflow dispatch during this task;
no P12/private key/password/API key needed for profile/public-certificate matching.
Tests: fictional input, exact scope/repository/SHA, fail-closed environment protection,
bounded secret transport/no output, timeout/uncertainty and native validation integration.
Blockers: unapproved custody expansion, inability to protect private input or establish
exact target/time/one-shot semantics; do not pretend generic architecture equals execution approval.

TASK183 permits future protected Environment Secrets -> ephemeral runner architecture
only within a separately reviewed signing design; actual access/Secret configuration
requires exact Owner release. Assess whether verification-only preparation fits this
already approved design or needs a new custody decision BEFORE implementation.

Proposed minimal transport would carry only existing public distribution certificate,
downloaded profile and expected Team identifier in one bounded Environment secret to a
fixed manual macOS verification job. No private signing or upload keys. No public artifacts.
Public bundle remains the repository iOS bundle; no values appear in logs/chat.
Root/signature/content verification remains TASK189, no caller trust override.
Environment must exist and have exact branch/reviewer protections before any private
write/read. Local wrapper would read fixed protected same-handle inputs only AFTER
metadata preflight and exact confirmation; unknown operation outcome never auto-retries.

Advisor must assess a complete feasible scope, including secret retention/cleanup,
trusted workflow/dependency execution, one-shot binding and actual authorization; flag
if a decision is needed now. Do not implement a partial transport that merely moves the
blocker. Planning may remain local without a status-only PR. No writer dispatched yet.

## Lifecycle correction for advisor lease2

Lease1 REQUEST_CHANGES complete: software prep is within TASK183, but lifecycle was
underspecified. Revised proposed contract follows; no live permission granted.

- Fixed repository r06521541/NTUBTOB-management-system, existing Environment
  ios-profile-verification, workflow ios-profile-verification.yml, ref main only.
  Preflight verifies exact remote/local full SHA, expected workflow, required Owner
  reviewer, no admin bypass and only main branch policy. Unknown protection STOP.
  No Environment creation/repair or permission edits in wrapper.
- Use documented GitHub REST API version 2026-03-10 dispatch response (HTTP200 with
  workflow_run_id) to bind exact run BEFORE a single Secret PUT. Only one dispatch;
  non-200/timeout -> uncertain STOP, NO upload. Never infer a run id by guessing/latest.
  Required Environment approval prevents access before Owner approves; wrapper says
  approve only after upload is confirmed. Early approval/missing input fails closed.
- Single bounded versioned envelope in fixed IOS_PROFILE_VERIFICATION_INPUT avoids
  multi-secret partial writes. It includes only profile/public certificate/expected
  Team plus random nonce, exact SHA, returned run_id and expiry (60 minutes).
  This is NOT field masking/end-to-end encryption. It is private data within GitHub's
  approved custody boundary. No raw/derived value logged, echoed, arguments or artifact.
- Secret must be absent initially; never overwrite a pre-existing value. Local same-
  handle metadata checks hold only distribution.cer/distribution.mobileprovision in
  the existing protected local directory; never open CSR/P12/private key/API key.
  Read payload/hidden Team only after exact visible action and confirmation.
- Job pre-guards main/repository/event/SHA/run_attempt=1. Runner checks envelope
  run_id==GITHUB_RUN_ID, nonce/input equality, exact SHA and unexpired aware time before
  native verification. Another dispatch/rerun cannot verify the same envelope.
  Secrets are not literally read-once; do not claim durable cryptographic consumption.
- Dependencies/actions fixed; install and compile public native helper before private
  input processing. Never pass private environment to compiler/subprocesses. Separate
  preparation/verification phases reuse TASK189 constraints without weakening them.
  Contents read-only, no privileged runner token, caches, public artifacts or keychain.
- Wrapper observes only exact returned run metadata for <=45 minutes then cleans up
  the one Secret it attempted to create, including runner/dispatch failure. DELETE is
  one attempt followed by bounded metadata absence confirmation. PUT uncertainty or
  DELETE ambiguity remains retention_unresolved even if an immediate GET says absent;
  no retry of PUT/dispatch. User must reconcile via separately scoped manual cleanup.
  Normal success requires native job success AND confirmed Secret absence.
- Process death/offline/forced kill may leave Secret. Expiry blocks validation but
  does NOT delete GitHub Secret. Owner remains retention owner and must accept this
  risk at exact release. No persistent watchdog or high-privilege runner PAT added.
- Scope should include complete intake/controller, runner, workflow, focused tests,
  hash-locked isolated dependencies, fictional end-to-end native integration, CI and
  runbook. No live operation or signing/upload. This is a proposal until lease2 accepts.

Advisor task-190-security-20260910 lease2: read-only architecture correction,
report_to /root. Official dispatch API source:
https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event

## Accepted implementation assignment

Advisor lease2 ACCEPT, complete. Before PUT additionally prove returned run's exact
repository/workflow/event/main/head_sha/attempt and waiting-for-review state; reject
early execution/completion. Recheck main and Secret absence immediately before PUT.
Local exclusive lock plus Owner single-writer/no-manual-edit contract; no remote CAS
claim. Entire encoded envelope <= GitHub48KiB single Secret cap; no split workaround.
Success requires exact named native verification job success, not only aggregate run.

- Type now delivery. Writer /root/csr_writer, codex-writer,
  claim task-190-writer-20260910 lease1, write allowed, report_to /root.
- Writer owned: tools/ios_profile_intake.py, tools/ios_profile_verification_runner.py,
  tools/tests/test_ios_profile_intake.py, tools/tests/test_ios_profile_verification_runner.py,
  .github/workflows/ios-profile-verification.yml, docs/coordination/reports/TASK-190.md.
- Main owned: this task/HANDOFF/PROJECT_STATE, docs/releases/IOS_CLOUD_BUILD_RUNBOOK.md,
  tools/requirements-ios-profile-intake.txt, existing two CI workflows and CI contract test.
- Reuse existing custody.Native metadata/ACL/same-handle guards without opening its
  hardcoded packaging inputs. Do not change existing packaging/custody/CMS trust tools.
  Prepare code-only native binary before Secret step using existing compiled production
  helper; separate runner verification/cleanup phases with no private files/cache/artifacts.
- Fixed filename distribution.mobileprovision is a future Owner copy into protected
  local folder, not an instruction to search/copy now. Existing distribution.cer unchanged.
- No source mutating command, live preflight/PUT/dispatch/delete or environment setup
  may be run by writer. All controller tests use mocked GH plus fictional temp assets.
  Actual fictional runner/macOS coverage via existing CI must precede merge.
- Mandatory ACK/heartbeat/proactive final packet per COLLABORATION2; writer delivers
  dirty changes then becomes read-only. Independent review before one PR/fullCI/merge.

Lease2 failure-cleanup clarification ACCEPT: for a successfully returned and identity-
verified exact run only, failure cleanup may issue one ordinary cancel POST if it is
not terminal. No force/retry/guessed-id cancel. Bounded terminal confirmation; an accepted
cancel does not itself prove termination. Track cancellation ambiguity separately and
never let it prevent Secret DELETE for this operation's PUT attempt. Before-PUT failures
must NOT delete any Secret. Owner gate includes cancel-on-failure and memory-retention
limits: deleting Secret does not clear a runner that already received input.
Read/validate payload after local confirmation but before dispatch to avoid creating a
waiting run for malformed input. Default preflight remains metadata-only.

## Unverified live compatibility boundary

Official GitHub OpenAPI Environment schema checked 2026-09-10 does not document
`can_admins_bypass`. The explicit-false runtime guard remains fail closed; mock
fixtures cannot establish live API visibility. No live preflight has been run.
Software acceptance must not be described as live execution readiness. Before any
private execution release, resolve protection observability with bounded read-only
metadata evidence; missing/unknown remains STOP, never relaxed or retried as mutation.

## Independent implementation review

Writer lease1 completed and is read-only. Advisor /root/task181_review,
claim task-190-security-20260910 lease3, role advisor, write read-only, owned_paths none,
report_to /root. Branch/base/head remain those above; review entire TASK190 dirty
delivery including Main CI/lock/runbook integration and writer report. Mandatory
COLLABORATION2 packet applies. Stop on scope/custody expansion, unsafe failure paths,
unverifiable evidence or changed implementation during review. No live queries or
mutations. Give ACCEPT/REQUEST_CHANGES for software separately from live readiness;
explicitly assess the protection-field compatibility limit before hosted spend.

Lease3 ACCEPT complete: source has no blocking implementation findings; one hosted
fictional CI is permitted, live readiness is not established. Main owns the final
review record and integration. Independent 36 tests: 35 PASS/1 macOS skip, missing
protection mocked GET-only STOP and diff check PASS. Main affected 127 tests passed
with 4 platform skips; final focused 36 tests passed with 1 skip; 5-file quality PASS.
Actual macOS rehearsal and hash-lock installation must pass before merge. Local YAML
parser unavailable (PyYAML absent); hosted parsing remains required.
