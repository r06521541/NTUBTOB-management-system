# TASK-184 report

Base `9eb816613934a2517b70a828b4bcdd47a25a9ee6`; branch `codex/task-184-windows-ios-csr`.

## Delivery boundary

Windows local-only CSR/encrypted PKCS8 operator with exact clean checkout,
native known-folder/fixed-drive/reparse/repository safeguards, protected ACL
before generation, hidden inputs and exact in-process one-shot confirmation.
No overwrite, partial output retained, fixed sanitized result. Saved upload
API p8 is not read. Actual Owner operation still requires release; tests only
generate fictional temporary assets. No Apple/certificate/sign/upload action.

## Evidence checkpoint

- Writer `/root/csr_writer` reported 18 focused tests PASS including real Windows
  ACL/known-folder/fixed-drive fixtures in disposable temporary directories.
- Initial sandbox ACL test rejected with UnauthorizedAccessException before
  key generation. Identical ACL code passed controlled test outside sandbox;
  no permission guard was relaxed and no Owner target was used.
- Minimal child environment implemented: native-derived SYSTEMROOT/WINDIR, fixed module path and target/action data only. Sentinel-forwarding regression added; writer final focused suite 19 PASS, quality/diff PASS, Main received completion.
- Existing CI contracts: 35 total, 34 PASS, 1 local Bash-dependent skip.
- Hosted deployment-tools gate now has Linux/Windows matrix: both run scoped
  certificate tests, existing unrelated deployment/release suites stay Linux.
  Aggregate final gate unchanged; no quick exemption or permission elevation.
- Main independently reran focused19 (including native Windows fixture) PASS; working-tree quality3 Python paths and diff check PASS.
- Independent Security reviewer `/root/task181_review`: ACCEPT, focused19 PASS in allowed native ACL test environment, diff PASS; Main received/accepted and reviewer claim complete. Immutable commit/hosted integration pending; later Git/PR evidence supersedes this checkpoint, not Owner gates.

## Hosted Windows correction checkpoint

- PR #239 initial head `8c99782c2584871a8b16a014ca789a7cd02fcd56`, run34236530908: Linux certificate/deployment gate PASS; Windows native ACL fixture timed out in the fixed PowerShell child after30s. Subsequent negative ACL verification took25s. No real Owner operation was run.
- Writer lease2 investigates native child startup environment and bounded timeout, without weakening ACL or automatically retrying material operations. Cause beyond observed timeout remains unproven until corrected hosted evidence.
- Correction supplies only native KnownFolder LOCALAPPDATA and its existing local non-reparse Temp as TEMP/TMP, preflighted before input. Missing Temp rejected rather than created; no caller environment forwarding, same30s timeout/ACL. Native focused20 PASS; source correction pending hosted confirmation, not a proven explanation of the original timeout.
- Independent lease2 correction review ACCEPT; reviewer reran20 native tests PASS and diff check PASS; Main acknowledged. No more unbounded corrections/retries for the same hosted blocker.

## Remaining limits

### Reopened diagnostic evidence

- Corrected head `d8edafdf977c5ac1617a12a52e1587b6c811b622`,
  run34237455594: Windows again timed out at30s in ACL establishment; all
  other substantive jobs passed, final gate failed. PR239 remains unmerged.
- Owner requested continued investigation. Main native local probes separated
  PowerShell startup, explicit Security module import, identity resolution and
  temporary-directory ACL set/read/rule checks; each completed within about1s.
  This does not establish the hosted cause. No genuine key was generated.
- Lease3 adds fixed test-only stage evidence for one hosted diagnostic run;
  operator safeguards and30s timeout remain unchanged. No blind retry of real
  operations and no weakening of key custody.
- Lease3 writer and independent Security reviewer each ran23 native tests PASS;
  review ACCEPT, quality/diff PASS. Main independently checked diagnostic3 PASS
  and zero operator diff, received both final packets; claims complete.

No live CSR accepted by Apple, genuine private key creation, imported
certificate, PKCS12 conversion, GitHub Secrets, TestFlight upload or device
evidence. Python cannot guarantee memory zeroization; ACL does not defend
against same-user malware/admin or replace secure backup. Git/CI only external
integration; no cloud/account/production mutation.
