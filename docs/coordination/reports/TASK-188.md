# TASK-188 writer report

- Branch: `codex/task-188-native-pkcs12-compatibility`; unchanged HEAD
  `e18f376f51ca755d1305052fe2f0ec13d0c175f4`; writer lease 1, no commit/push.
- Added only the assigned Swift harness, Python fixture orchestrator, tests and this report.
  Main owns the existing dirty workflow/CI/task/HANDOFF/state/runbook integration.
- No-argument entry: `python -m tools.ios_pkcs12_compatibility`. Windows/Linux entry
  returns fixed PLATFORM_UNSUPPORTED, never success; macOS requires version 15+ and an
  SDK compiling the actual `kSecImportToMemoryOnly` constant. No string-key fallback.
- Python generates a wholly fictional RSA chain/CSR/encrypted PKCS8 in memory and calls
  the unchanged `package_material` core. No duplicated PKCS12 encryption recipe.
  Only compiled code occupies an automatically cleaned temporary directory.
- Swift accepts bounded stdin frames, fixed fictional password selectors and no arguments.
  Memory-only import requires exactly one identity, exact leaf DER and an in-memory
  signature challenge verified against that certificate. Returned trust is never evaluated.
  No keychain/store/network/real input path or persistent private output exists.
- Cases require successful import, wrong-password AUTH_REJECTED, certificate mismatch and
  oversized-frame rejection. Malformed and tail-tampered P12 accept only AUTH_REJECTED or
  DECODE_REJECTED: OS decoding order is not a trust guarantee; no crash/timeout/generic
  import failure counts as negative evidence. Tail mutation is not described as a MAC-byte edit.
- Native stdout is read at most 129 bytes (128-byte contract), stdin is bounded, subprocess
  lifetime is bounded and no raw stderr/exception/payload is emitted. Fixed case stages aid
  diagnosis. All real-asset/CMS/trust/private-possession/signing/upload/release flags remain false.

## Writer evidence and limits

- `py -3.10 -m unittest tools.tests.test_ios_pkcs12_compatibility -v`: 9 run,
  8 PASS, 1 explicit native macOS skip on Windows. Includes actual bounded fictional
  child pipes, production packaging round-trip, strict negative contracts and no disclosure.
- Owned Python `repository_quality format` / `check` and `git diff --check`: PASS.
- An intermediate fictional Windows child failed with a minimal macOS environment;
  its test adapter now forwards only SystemRoot to the test Python child. The macOS
  harness environment/security contract was not relaxed.
- Main separately reports packaging/profile/workflow contract 34 tests PASS, skip 1.
  This is attributed Main evidence, not a duplicate writer run.
- Swift compilation and actual SecPKCS12Import have **not** run locally (Windows).
  Main's mandatory hosted macOS entry plus independent acceptance remain required.
  A compile/import mismatch stops; it does not authorize a persistent fallback or retry
  with real assets. Python/Swift memory is not claimed to be zeroized.
- External mutations: none. No real Owner assets, keychain operations, cloud/store calls,
  commits or pushes. Fictional private data never written as a file.

API boundary reference: [Apple SecImportExport.h](https://raw.githubusercontent.com/apple-oss-distributions/Security/main/keychain/headers/SecImportExport.h).

## Main acceptance checkpoint

Independent reviewer lease 2 ACCEPT, no blocking findings; 23 tests ran with 21 PASS
and two explicit environment/platform skips. Main received the completion packet.
Main's working-tree quality check passed all three Python files. Actual macOS compile
and import remain pending hosted evidence; same PR immutable evidence supersedes this
pre-CI checkpoint, never the private-operation gates. No signing/upload authorization.
