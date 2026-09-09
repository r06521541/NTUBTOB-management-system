# TASK-186: Safe local Apple certificate packaging

- type: delivery; delivery_group: task-186-ios-certificate-packaging; risk: L3
- base: `f8c21fef3dc964b3df19121dc72d23d7f76a1f3b`
- branch: `codex/task-186-ios-certificate-packaging`
- Main `/root`, claim task-186-main-20260909 lease1, owns coordination/runbook/CI.
- Owner requests implementing the next safe intake, trust and encrypted packaging
  step. Development uses fictional inputs only; no actual Owner file inspection,
  key decryption, conversion, signing, Apple API, upload or Secret access.
- TASK185 merged PR240 with full CI34313053719 PASS. Prior claims complete.
- Owner reports CSR creation succeeded at the base SHA, Apple Distribution
  certificate issued and downloaded. These are reports, not independent checks.

## Architecture review first

Reviewer `/root/task181_review`, advisor/read-only, claim
task-186-security-20260909 lease1, no owned files, report_to `/root`.
Mandatory COLLABORATION section2 ACK/heartbeat/blocker/proactive final applies.
Review a minimal fail-closed design before writer assignment: fixed private local
directory from TASK184, bounded non-reparse file handles and restrictive ACL,
no raw output, no caller trust anchors; explicit pinned Apple chain/purpose
verification; hidden decryption/new encryption passwords only in a future
Owner execute; matching CSR/certificate/private key; exclusive encrypted PKCS12
output, no plaintext private file, no overwrite/retry after uncertainty.
Offline verification must not claim revocation, Team/App/profile or signing
authority. Investigate public official Apple PKI sources, not Owner assets.

Main researches official sources and maintains scope concurrently. Implementation
claim follows accepted architecture. Tests must cover fictional crypto and native
Windows file/ACL boundary plus Linux pure core. A reviewed exact SHA and a new
Owner one-shot gate are required before any real operation. Preserve existing
CSR and encrypted key; never regenerate or read them in development.

Reviewer architecture lease1 completed and Main received it. Reviewer same
claim lease2 now performs read-only implementation review concurrently with
writer's final focused tests; final acceptance requires writer completion and
verification of the final frozen diff. No writer-owned edits by reviewer.
Writer lease1 completed; Main received21 run/20 PASS/1 symlink privilege skip
(native junction covered). Implementation frozen for independent lease2 review.
Independent lease2 ACCEPT received with21 run/20 PASS/1 symlink privilege skip;
both claims complete. Main integrates one PR/full hosted gate under standing
Git authorization. No actual private operation authorized by merge.

Stop on actual private input need, unprovable trust policy, unrelated overlap,
required weakening of safe file custody or external mutation.

## Accepted implementation contract

Architecture lease1 ACCEPT received. Writer `/root/csr_writer`, codex-writer,
claim task-186-packaging-writer-20260909 lease1, report_to `/root`, owns only
`tools/ios_certificate_packaging.py`, `tools/ios_certificate_custody.py`,
`tools/tests/test_ios_certificate_packaging.py`,
`tools/tests/test_ios_certificate_custody.py`. No commit; Main integrates.
Main additionally owns `tools/apple_distribution_trust.py` public pinned anchors.
Use native Windows same-handle final path/file identity/ACL/size verification,
reject reparse/multiple links, lock directory rename and input write/delete.
No private input before exact confirmation. Fixed files in existing TASK184
directory: distribution.cer, distribution.csr, distribution-private-key.pem;
exclusive new distribution.p12. Never change existing ACL/files. No repair mode.
Read-only preflight is metadata only; actual private intake is Owner-only.
No path/private values as CLI/env, no network/system trust fallback.

Official Apple WWDR CPS1.32 section4.11.24 specifies SHA2/RSA, critical digital
signature KU/codeSigning EKU/CA=false and both critical submission markers
1.2.840.113635.100.6.1.4 and .7. Apple WWDR help maps Apple Distribution to G3.
Main supplies fixed Apple Root and WWDR G3 PEM/pins from official Apple PKI.
Pure core may inject fictional chain in tests; CLI cannot accept trust override.
Explicit offline scope: revocation, Team, App/profile, signing/upload/release
remain false. Unknown critical extensions/algorithms fail closed. Root pinned
self-signature may use its actual legacy SHA1 algorithm, never permit SHA1 leaf.

Preserve original material. Output once with restricted verified handle,
encrypted PKCS12 only, readback validation; after create attempt any failure is
uncertain and no retry/delete. Fixed ASCII stage/reason only. Native fictional
tests plus pure crypto positive/negative, no real file tests. Reuse TASK184
dependency/hidden-input primitives where safe, not its path-only ACL reader.
