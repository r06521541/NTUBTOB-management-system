# TASK-183：iOS cloud rehearsal and artifact-only inspection

- type: delivery; delivery_group: task-183-ios-cloud-rehearsal; acceptance_level: L3
- Owner request: 2026-09-08 continuous repository delivery through review/CI/merge, stopping at external Owner gates.
- base: `e6fe9b9e7612831cdd5fa75defe9ce022db846e6`
- branch: `codex/task-183-ios-cloud-rehearsal`
- actor_id: `/root`; role: main-work; claim_id: task-183-ios-cloud-rehearsal-20260908
- lease_version: 1; write: allowed; report_to: `/root`
- TASK-182 is merged in base; its writer/reviewer claims are complete.

## Scope / owned paths

- `tools/ios_candidate_inspector.py`, `tools/tests/test_ios_candidate_inspector.py`: explicit artifact-only inspection; retained signature/profile/entitlement checks plus rejecting application debugging entitlements; never upload authority.
- `tools/ios_release_pipeline.py`, `tools/tests/test_ios_release_pipeline.py`: secret-free, deterministic rehearsal of staged build/inspection/upload lifecycle, exact commit contract, cleanup/failure/no-retry semantics. No live adapter or private input.
- `.github/workflows/flutter-tests.yml`, `.github/workflows/python-tests.yml`: exercise rehearsal in existing hosted gates without additional signing workflow, secrets, permissions or paid runner; explicitly restore pinned iOS engine when hosted SDK cache lacks release frameworks.
- `docs/releases/IOS_CLOUD_BUILD_RUNBOOK.md`, `docs/releases/IOS_TESTFLIGHT_CHECKLIST.md`, `clients/flutter_app/ios/README.md`: phased workflow, actual remaining gates, Owner-reported Apple records.
- This task, `docs/coordination/reports/TASK-183.md`, `docs/coordination/HANDOFF.yaml`, `docs/coordination/PROJECT_STATE.md`.

## Owner-approved narrow design exceptions

Owner explicitly accepted separating artifact integrity inspection from release eligibility. Default TestFlight gate remains blocked by committed readiness; artifact-only never authorizes upload, distribution or production. Do not alter readiness marker or build validators.

Owner accepted future protected GitHub Secrets -> ephemeral hosted runner -> temporary keychain/necessary private files -> cleanup architecture, overriding the general environment/temp-file prohibition only for that reviewed signing design. This delivery uses fictional data only. Actual key creation/access, Secret configuration, signing and store upload require a later exact Owner release and reviewed live wrapper; this exception does not authorize them now.

## Invariants / verification budget

- Staging/real/Basic only; no provider/backend/data/schema change or public release.
- Rehearsal explicitly fictional, no credentials, subprocess, network, real archive, signing or upload. Cannot return live PASS or reusable approval. Real actions stop before adapters/inputs.
- Exact full SHA; mismatch before staging; cleanup on every attempted staging path; simulated timeout/uncertain never retries; failed cleanup is explicit, not success.
- Independent safety architecture review before hosted work, focused inspector/pipeline tests and existing CI contracts, quality check, diff check, one ready PR and required hosted gates.
- Owner App ID/capability and App Store Connect record are reported created, not newly verified. No recreation.

## Reviewer claim

- actor_id: `/root/task181_review`; role: advisor; claim_id: task-183-security-review-20260908; lease_version: 2
- owned_paths: none; write: read-only; report_to: `/root`
- Scope: architecture then exact diff independent Security/Release acceptance. Lease 1 ACCEPT received; 37 independent tests PASS. Lease 2 pinned iOS engine pre-cache and regression review ACCEPT; Main acknowledged and claim complete. Final hosted gate pending.
- Follow COLLABORATION section 2 packet: immediate received/executing ACK; heartbeat every 10–15 min, blocker immediately; final SHA/dirty paths/tests/findings/limits/external mutations sent proactively to `/root`.

## Stop conditions

Real signing/store/Secret/account/paid actions; unsafe requirement expansion; unrelated dirty conflict; unresolved safety finding. Main tracks reviewer until final packet is received; no passive waiting for Owner.
