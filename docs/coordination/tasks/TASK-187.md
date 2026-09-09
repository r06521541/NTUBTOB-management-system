# TASK-187: iOS profile validation and signing preparation

- Type: delivery; delivery_group: task-187-ios-profile-signing-preparation; risk: L3.
- Branch: `codex/task-187-ios-profile-signing-preparation`.
- Base/head: `c458d29326072444987fff70b43aa3ec46a5bfa1`.
- Main: `/root`, role `main-work`, claim `task-187-main-20260910`, lease 1.
- Main owns this task, HANDOFF, PROJECT_STATE and integration documentation.
- Advisor: `/root/task181_review`, role `advisor`, claim `task-187-security-20260910`, lease 1;
  owned_paths: none; write: read-only; report_to: `/root`.
- Mandatory packet/ACK/heartbeat/completion: COLLABORATION section 2.

## Evidence and scope

TASK-186 merged PR241 at the base above with full PR CI34372531298 PASS.
Owner reports approved P12 packaging confirmed_success and profile download.
These reports are not new inspection; never repeat package generation. Prior claims complete.

Goal: independently review the smallest executable profile validation/signing preparation scope.
Core files: existing iOS candidate inspector and release pipeline; writer paths deferred.
Invariants: no real private inputs; decoding/correspondence never implies trusted signing readiness.
Tests: fictional adversarial fixtures and affected safety suites after architecture acceptance.
Blockers: unprovable trust, unsafe custody/cleanup, missing authority or unrelated overlap.

Distinguish CMS decoding, CMS signature/trust, App/Team/certificate/entitlement matching,
PKCS12 import compatibility and actual signing readiness. No hand-rolled CMS cryptography;
do not assume `security cms -D` establishes Apple trust. Prefer maintained native verification.
No real profile/P12/API key/password reads, keychain, Secret configuration, signing, upload,
Apple mutation or paid runner operation. Fictional native rehearsal/workflow implementation
requires architecture acceptance first. Existing production/provider guards remain unchanged.
Main researches official sources alongside the advisor; sole writer scope follows acceptance.
Independent final review, focused tests and one PR/required CI precede merge.

## Accepted implementation boundary

Security architecture lease 1 ACCEPT: implement only a pure in-memory decoded-plist
correspondence core; defer CMS intake/trust, native PKCS12 import and cloud workflow.
The core has independent diagnostic value but cannot validate Owner's downloaded CMS file.
No filesystem/subprocess/network/CLI or caller-supplied trust flags in the core.
Input: bounded decoded plist bytes, exact expected bundle/team and certificate DER, aware time.
First delivery accepts XML plist only; standard Apple external DTD may be recognized but never
resolved. Binary plist and other DTD/entity declarations are explicitly rejected.
Reject duplicate keys, ambiguous types, entities/unsafe DTD, trailing objects, invalid dates,
wildcard App IDs, mismatched Team/prefix/entitlements/certificate, development/device profiles.
Success is PROFILE_CONTENT_MATCH_ONLY; CMS/trust/revocation/private-key/native-import and
signing/upload/release flags remain false. Include adversarial and no-disclosure/no-I/O tests.

- Writer: `/root/csr_writer`, role `codex-writer`, claim `task-187-writer-20260910`, lease 1.
- owned_paths: `tools/ios_profile_validation.py`, `tools/tests/test_ios_profile_validation.py`,
  `docs/coordination/reports/TASK-187.md`; write allowed; report_to `/root`.
- Main retains workflow, CI contract, runbook, task/HANDOFF/PROJECT_STATE edits.
- Advisor lease 1 complete; independent implementation review needs a fresh lease.
- Writer must not commit shared Main changes; deliver exact dirty paths/tests for Main integration.

Writer lease 1 complete; Main received final packet. Advisor claim
`task-187-security-20260910` lease 2 assigned to `/root/task181_review` for independent
review of all current TASK-187 paths; read-only, report_to `/root`, no owned writes.

Advisor lease 2 ACCEPT received: no blocking findings; independent pure suite 8 PASS
and diff check PASS. Both agent claims complete. Main owns final commit/PR/CI integration.
