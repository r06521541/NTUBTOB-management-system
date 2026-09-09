# TASK-186 evidence

Base: `f8c21fef3dc964b3df19121dc72d23d7f76a1f3b`; clean main verified before
creating `codex/task-186-ios-certificate-packaging`. No Owner asset inspected.

Architecture review: task-186-security-20260909 lease1 ACCEPT, completion
actively received by Main. Native same-handle custody and constrained offline
trust mandatory; no generic TLS policy/system trust or private-file fallback.

Main retrieved only public Apple PKI root and WWDR G3 from official URLs recorded
in `tools/apple_distribution_trust.py`. Original DER SHA256 matches both pinned
PEM constants. Explicit RSA verification of root self-signature and G3 signature
PASS. Generic cryptography `verify_directly_issued_by` rejects legacy root SHA1;
explicit verification is limited to the pinned root, never a SHA1 leaf exception.

Preliminary checks before writer handoff:
- `py -3.10 -m unittest tools.tests.test_ci_workflow_contract -q`:14 run,1
  platform skip, otherwise PASS.
- `py -3.10 -m unittest tools.tests.test_ios_certificate_pair tools.tests.test_ios_release_pipeline tools.tests.test_ios_candidate_inspector -q`:41 PASS.
- Quality on Main public trust module/CI contract and `git diff --check`:PASS.

Writer final received: four new implementation/test files, no commit. Focused
`py -3.10 -m unittest tools.tests.test_ios_certificate_packaging tools.tests.test_ios_certificate_custody -q`:
21 run,20 PASS,1 Windows symlink privilege skip; native junction rejection PASS.
Native write/delete/rename locks, null file DACL, hardlinks/size, partial output,
flush and ACL failures covered. Crypto checks/roundtrip/no-password rejection,
wrong password, expiry/algorithm/purpose/critical extensions and fixed reasons
covered. Owned four-file quality and diff PASS. Independent lease2 reviews the
frozen implementation. Main has received completion and writer is read-only.

Independent Security lease2 ACCEPT received, same focused suite independently
21 run/20 PASS/1 symlink privilege skip. No blocking findings. Main integration
suite55 run/1 platform skip otherwise PASS; working-tree quality6 files PASS.
Hosted CI pending. Actual certificate/key validation,
conversion, Apple/profile/cloud signing/upload remain unperformed and ungated.
Owner reports issuance/download; this is not independently verified evidence.

First PR241 run34369544503 at431e71b4f62c0346591dc56541e25ca17c75ac14:
Windows four native tests rejected directory metadata before I/O. Writer locally
reproduced an8.3 temp alias versus same-handle canonical final path mismatch.
Test fixtures now resolve the existing temp root; a regression proves aliases
still reject and canonical paths accept. Production custody is unchanged.
Native10 run/9 PASS/1 symlink privilege skip; explicit alias and junction PASS.
Independent lease3 delta review and corrected same-PR CI required before merge.
Lease3 ACCEPT received; independent native10 run/9 PASS/1 symlink skip. Product
modules unchanged, diff check PASS. Main proceeds one corrected same-PR run.

Corrected run34370291133 at6beeaac3d1321b8ec989eb16d10bb1a4a45bdfb0:
Windows60 tests,4 errors at native file ACL check (line234), after directory
metadata passed. This is not the prior short-path mismatch. Root cause remains
unproven: owner SID mismatch or missing DACL/owner needs categorical fixture-only
diagnosis. Do not infer that elevated runner ownership is proven. No further
blind retry or real Owner run; PR241 is unmerged. Next scope must explicitly
resolve native fixture ownership versus operator custody, independently reviewed.
Current implementation cannot be handed to Owner as ready. Main retains local
blocked handoff; no separate coordination-only PR/CI run.

Owner resumed the blocked work. Microsoft native ownership documentation shows
that unspecified owner comes from the creator token; parent ACL inheritance
does not guarantee the current-user owner required by custody. Security lease4
architecture ACCEPT: explicit CREATE_NEW owner/protected DACL, no repair of
existing inputs or ACL relaxation. Writer lease3 implements the native creation
boundary plus independent fictional metadata checks. Fixed boolean diagnostics
will distinguish default token owner from user without outputting any SID.
Prior corrected CI otherwise passed all required jobs; its final gate failure
was downstream of Windows tools. No genuine private operation is released.
Writer lease3 complete and independent lease5 ACCEPT received. Both native suites
14 run/13 PASS/1 symlink privilege skip; packaging12 PASS; Main integration26
run/1 platform skip otherwise PASS. Explicit current-user owner/protected DACL
and noninheritable returned handle verified by native independent queries;
descriptor failure never calls CreateFile, wrong-owner still rejects. Quality
and diff PASS. Local diagnostic four booleans true; hosted mismatch remains
unconfirmed until the evidence-bearing next run. Existing files are never repaired.
