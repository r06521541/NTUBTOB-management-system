# TASK-188: Native PKCS12 compatibility preparation

- Type: delivery; delivery_group: task-188-native-pkcs12-compatibility; risk: L3.
- Branch: `codex/task-188-native-pkcs12-compatibility`.
- Base/head: `e18f376f51ca755d1305052fe2f0ec13d0c175f4` (TASK-187 merged PR242,
  full CI34378959382 PASS). Prior claims complete.
- Main `/root`, role main-work, claim task-188-main-20260910 lease 1; owns task,
  HANDOFF, PROJECT_STATE, runbook, workflow and CI integration tests.
- Advisor `/root/task181_review`, role advisor, claim task-188-security-20260910
  lease 1; owned_paths none; read-only; report_to `/root`.
- Assignment ACK/heartbeat/proactive completion: COLLABORATION section 2.

## Architecture checkpoint

Goal: prove TASK-186 encryption format imports through real macOS Security APIs using fictional assets.
Core paths: native fixture harness, generator/test, existing hosted macOS workflow; exact writer paths after review.
Invariant: no real assets, no persistent keychain or trust store writes, no signing/upload authority.
Tests: same AES256/SHA256 PBESv2 parameters, correct/wrong password and corrupted input, fixed safe results.
Blocker: unsupported memory-only API, ambiguous side effects, unreviewed asset custody or unexpected dirty overlap.

Apple's SecImportExport.h documents kSecImportToMemoryOnly=true from macOS15.
Require that runtime/SDK explicitly; never fall back to default SecPKCS12Import,
which stores identities in the macOS default keychain. Return one exact identity
and certificate match; do not use returned trust as Apple verification. A fictional
in-memory challenge may prove private key usability, not app code-signing readiness.
No private fixture payload/log/artifact export. Fictional generated inputs may flow
through bounded stdin pipes only; binary build output contains code, not keys.
No Owner P12/profile/API key/password reads, keychains, cloud Secrets, store or release
operations. Existing free standard hosted macOS CI may run reviewed fictional tests.

Main researches CMS native trust separately; do not ship a generic decoder as trusted
profile verification. CMS authenticity/purpose and real asset intake remain independent
gates until a defensible native verification design is accepted. No hand-rolled CMS.
One writer and independent final acceptance precede one PR/required CI and merge.

## Accepted scope / writer

Advisor lease 1 ACCEPT received. Require macOS15 runtime and SDK; actual constant
kSecImportToMemoryOnly=true, no fallback or trust evaluation. Bounded framed stdin,
fixed fictional passwords, fixed binary/source location, captured allowlisted output
and subprocess timeout. Never accept a real-input path/secret/CLI option. Verify
exact one identity, certificate DER and optional in-memory challenge; negative tests
must return expected categories, not treat arbitrary crashes as rejection evidence.
Generate fictional chain/CSR/encrypted key in memory and call existing
`ios_certificate_packaging.package_material` for exactly the production encryption
format; do not modify the real packaging operator or duplicate its encryption recipe.
Result FICTITIOUS_NATIVE_IMPORT_VERIFIED keeps real assets/CMS/trust/signing/upload false.

- Writer `/root/csr_writer`, role codex-writer, claim task-188-writer-20260910 lease 1.
- Owned: `tools/native/ios_pkcs12_memory_import.swift`, `tools/ios_pkcs12_compatibility.py`,
  `tools/tests/test_ios_pkcs12_compatibility.py`, `docs/coordination/reports/TASK-188.md`.
- write allowed; report_to `/root`; deliver dirty files, no shared Main commits.
- Tests: positive, wrong password, corruption, expected certificate mismatch, oversized
  framing, unsupported platform, output/timeout guards and no real asset intake.
- Main wires macOS test into existing workflow and Linux/Windows offline contract suite.
  No additional hosted job/runner, uploads or artifacts. Code-only temp binary cleanup required.
- Advisor lease 1 complete; final review needs a new lease. Main retains integration paths.

Writer lease 1 complete; Main received completion. Advisor claim
task-188-security-20260910 lease 2 assigned to `/root/task181_review`: independent
full-delta review, read-only, owned_paths none, report_to `/root`.

Advisor lease 2 ACCEPT received; independent 23 tests ran (21 PASS, 2 platform/environment
skips). Both agent claims complete. Main may open the single PR as Draft because actual
macOS SDK/import evidence is unavailable locally; ready/merge only after hosted success.
