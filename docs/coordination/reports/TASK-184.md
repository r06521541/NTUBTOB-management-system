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

## Limits

No live CSR accepted by Apple, genuine private key creation, imported
certificate, PKCS12 conversion, GitHub Secrets, TestFlight upload or device
evidence. Python cannot guarantee memory zeroization; ACL does not defend
against same-user malware/admin or replace secure backup. Git/CI only external
integration; no cloud/account/production mutation.
