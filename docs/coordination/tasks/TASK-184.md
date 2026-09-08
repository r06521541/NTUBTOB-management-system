# TASK-184: Windows local Apple distribution CSR preparation

- type: delivery; delivery_group: task-184-windows-ios-csr; acceptance_level: L3
- Owner requested implementation 2026-09-08 after reporting Apple Certificates empty and upload API key safely saved.
- base: `9eb816613934a2517b70a828b4bcdd47a25a9ee6`; branch: `codex/task-184-windows-ios-csr`
- Main actor `/root`, claim task-184-main-20260908, lease 1, report_to `/root`.
- TASK-183 merged in base and main hosted run34151861595 succeeded; its writer/reviewer claims complete.

## Assignment / owned paths

- Writer `/root/csr_writer`, role codex-writer, claim task-184-csr-writer-20260908, lease 2, report_to `/root`, write allowed only:
  `tools/ios_certificate_preparation.py`, `tools/tests/test_ios_certificate_preparation.py`, `tools/requirements-ios-certificate.txt`.
- Main owns this task, single `docs/coordination/reports/TASK-184.md`, HANDOFF, PROJECT_STATE, `docs/releases/IOS_CLOUD_BUILD_RUNBOOK.md`, `.github/workflows/python-tests.yml`, `tools/tests/test_ci_workflow_contract.py`.
- Reviewer `/root/task181_review`, role advisor, claim task-184-security-review-20260908, lease 2, report_to `/root`, read-only, no owned paths.
- Mandatory COLLABORATION section2: immediate received/executing ACK; heartbeat10–15m; blockers immediate; proactively send exact HEAD/dirty/tests/findings/limits/external mutations to `/root`. Main waits actively.
- HANDOFF next_actor=codex-writer activates the sole implementation writer. Main may concurrently maintain only its listed coordination/docs/CI paths and perform read-only research; no overlapping implementation.
- Lease1 writer/reviewer completed and Main received ACCEPT/19 PASS. Lease2 writer completed native temp environment correction/20 PASS. Independent lease2 ACCEPT/20 native PASS received; both claims complete. Main pushes same PR; no private data or ACL weakening.

## Bounded deliverable

### Owner-reopened hosted diagnosis (2026-09-08)

Owner explicitly requested continued investigation after run34237455594 again
timed out at30s. This is a bounded diagnostic round, not an automatic mutation
retry: instrument the fictional native test with fixed stage labels only; keep
the production operator, timeout and ACL unchanged until evidence identifies
the blocked layer. No genuine assets or private inputs. One diagnostic push on
PR239; no unbounded reruns. Main local stage probes completed in about1s.
Writer `/root/csr_writer` lease3 owns only the existing certificate test file
for this round; previous implementation leases remain complete. Reviewer
`/root/task181_review` lease3 independently reviews diagnostic safety. Both
report to `/root` under the mandatory packet; Main owns task/report/HANDOFF.
Lease3 writer/reviewer completed,23 native tests PASS and diagnostic ACCEPT;
Main received both completion packets and resumes the single diagnostic push.

Repository-owned Windows-only operator: read-only preflight then explicit in-process one-shot Owner confirmation to create one RSA2048/SHA256 CSR plus encrypted PKCS8 private key in a newly secured local-only directory outside repository. Separate hidden common name/email/passphrase+confirmation; no CLI/env/private echoes, no fallback to visible input. Never overwrite/reuse existing output. Reject reparse/symlink/UNC/network/repository targets, dirty or SHA-mismatched repository, unsupported host/dependencies before private input. Set and verify restrictive Windows ACL before generating/writing private material. Fixed sanitized results and exact known filenames; partial failure preserves protected outputs and stops without automatic retry.

Use cryptography existing local 50.0.0 (scoped pinned tool requirements, not service dependency changes); stdlib/process safety, no custom cryptography. Test ephemeral fictional keys only; no Owner private input or genuine asset. No keychain, Apple upload, provider calls, certificate download, GitHub Secret, signing or deployment.

## Boundary / acceptance

Development and tests authorized now. Actual Owner run creating durable real key/CSR requires a later explicit exact approval after independent review/CI, not implied by this implementation request. Local encrypted private-file custody is proposed for that future operator, not permission to inspect Owner's saved API p8 or general secret paths.

Full focused offline crypto/path/ACL/hidden-input/confirmation/partial-failure/no-overwrite tests; independent Security review; CI Windows-specific behavior cannot be claimed from Linux tests. Scoped requirement/version and Python3.10 compatibility. One PR through normal hosted gate, no quick allowlist exemption. Stop on unknown unsafe key custody, actual external action, dirty overlap or reviewer blocker. No reuse of old approval packets or off-repository launchers.
