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
