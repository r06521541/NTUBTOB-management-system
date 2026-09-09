# TASK-185: Offline iOS certificate and CSR pair checks

- type: delivery; delivery_group: task-185-ios-certificate-pair; acceptance_level: L3
- Owner request2026-09-09: prepare subsequent steps while away; no real private input or signing.
- base: `47e832e685b68c0f50803decd989f36c38fc2651`; branch: `codex/task-185-ios-certificate-pair`
- Main `/root`, role main-work, claim task-185-main-20260909, lease1, report_to `/root`.
- TASK184 PR239 merged in base, PR CI34240299222 all PASS. Its writer/reviewer claims complete.
- Owner approved local CSR/key creation at the TASK184 exact SHA, but deferred until personally present for hidden inputs. Nothing created; approval does not migrate to a new SHA or authorize saved API key access.

## Scope and roles

Main owns task/report/HANDOFF/PROJECT_STATE, `docs/releases/IOS_CLOUD_BUILD_RUNBOOK.md`,
`.github/workflows/python-tests.yml`, `tools/tests/test_ci_workflow_contract.py`.
Writer `/root/csr_writer`, claim task-185-pair-writer-20260909 lease2,
owns only `tools/ios_certificate_pair.py`, `tools/tests/test_ios_certificate_pair.py`.
Reviewer `/root/task181_review`, advisor, claim task-185-pair-review-20260909 lease3,
read-only, no owned paths. Both report_to `/root`; mandatory COLLABORATION section2
ACK/heartbeat/blocker/proactive final packet applies. Architecture acceptance
before implementation; Main maintains nonoverlapping docs/CI and actively tracks.
Architecture lease1 ACCEPT received; writer active. Missing BasicConstraints is
not proof of CA=false: permit correspondence only with CA status unknown and all
trust/purpose gates still false; explicitly test/document this policy.
Writer complete:12 focused tests/quality PASS, proactive packet received by Main.
Reviewer lease2 now accepts the exact implementation independently; lease1
architecture review is complete. Writer remains read-only after handoff.
Lease2 review ACCEPT received. Main requests one observability improvement before
CI: distinct fixed reason codes for input/dependency/time/parser/CSR/key/validity/CA
failures, never raw details. Writer lease2 active for same two paths only; no
validation/trust relaxation. Independent delta review required after completion.
Writer lease2 completed13 tests/quality PASS; Main received completion. Reviewer
lease3 performs final reason-code delta acceptance; implementation writer idle.
Final lease3 ACCEPT received:13 tests PASS plus no-site-packages dependency
absence check. Both claims complete; Main proceeds final PR/CI/merge under
standing authorization, never real certificate/key/signing operations.

Pure in-memory byte-input certificate/CSR pair validator using existing pinned
cryptography50.0.0/Python3.10. Bounded single PEM or DER object, no trailing object
or junk, no file/path/private-key reader, no CLI execute/network/subprocess.
Validate CSR signature RSA2048/SHA256 (TASK184 scope), compare public keys,
check certificate UTC validity using explicit injected aware time; reject CA
certificates. Return only fixed classifications/reasons and authority=false.
No subject/email/serial/key/fingerprint/raw input or exception output.

Success is `PAIR_MATCH_ONLY`: it establishes public-key correspondence, not
private-key possession, certificate signature/chain/Apple trust/revocation,
team/App/distribution profile/capability or release readiness. All such gates
remain explicitly unverified; no caller-provided trust flag. A future reviewed
Owner wrapper must safely read real files. This delivery invokes only fictional
in-memory fixtures and does not modify the TASK184 creation operator.

## Verification and stop conditions

Focused positive/negative fictional crypto tests: PEM/DER, mismatch, bad CSR
signature, sizes/types/trailing data, invalid time/expired/future cert, CA,
wrong CSR algorithm, fixed no-disclosure result, no I/O. Independent Security
review plus quality/diff, existing Windows/Linux tool CI and required gates,
one PR under standing Git authorization. No service/schema/runtime changes.
Stop on need for actual files/private keys, external signing/store/paid action,
unsafe truth claims, unrelated dirty overlap or unresolved review finding.
