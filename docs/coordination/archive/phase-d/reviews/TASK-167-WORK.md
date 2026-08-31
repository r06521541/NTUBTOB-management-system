# TASK-167 Main Work review

## Verdict

`accepted_pending_hosted_ci`

## Accepted boundary

- The controlled staging debug build targets arm／arm64／x64 and requires one unique, non-empty, fully readable `libflutter.so` per ABI.
- Build and signer-check/install paths stream each runtime through CRC32 validation before package or signer acceptance. ABI-invalid candidates are removed and never reach ADB install.
- Existing detached snapshot, private defines, package, allowlisted debug signer, redaction, checksum and evidence-retention contracts remain unchanged.
- Borrowed-device evidence is limited to exact-package install and cold launch. No personal provider account, Secret, production or unrelated device data is in scope.

## Review evidence

- Independent Flutter/release-artifact review found and rejected two successive gaps: signer-check/install bypass plus zero-byte entries, then stored-entry payload corruption without CRC validation.
- Lease 3 final rereview: `ACCEPT`. The stored arm64 payload corruption regression rejected before package／ADB calls and removed the candidate.
- Focused ABI/build/install tests: 4/4. Complete launcher suite: 61/61. `git diff --check`: passed.
- Regenerated staging artifact checksum, package, signer and three-runtime matrix passed. Android 15／API 35 arm64 replacement install and bounded cold launch passed with no fatal app crash.

Hosted CI, PR/merge and final borrowed-device cleanup remain pending. Provider login was intentionally not performed and is not accepted as physical-device evidence.
