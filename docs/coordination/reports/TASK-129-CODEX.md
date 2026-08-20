# TASK-129 Codex report

- Base/HEAD before implementation: `9b87e1cb255924cbb0963e821556542f86f79688`
- Branch: `codex/task-129-staging-acceptance-harness-implementation`
- Scope: repository-only harness, direct mocked tests, and mobile runbook.

## Delivered behavior

- Added two explicit scenarios with no default multi-step mode and one
  deidentified JSON envelope per invocation.
- Added a versioned, atomic, non-secret checkpoint. It binds accepted SHA,
  artifact/signer hashes, package/version, AVD/serial, vocabulary version, and
  bounded result. Resume validates live binding and refuses a changed scenario
  or binding.
- Basic preparation verifies TASK-123 artifact provenance and conditionally
  uses only accepted actions: cleanup of drifted task evidence, build,
  signer-check, session-preserving install, and one cold launch. A matching
  build artifact still receives signer/install/cold on a fresh scenario because
  artifact provenance does not prove the installed APK; resume revalidates
  rather than reinstalling.
- Officer records durable intent/result/reconcile checkpoints around every
  grant, restore, and logout mutation. Unknown/crash resume is reconciliation
  only, never a mutation replay. The unprovisioned production broker boundary
  stops before broker/credential access with
  `OWNER_ACTION_REQUIRED/BROKER_PROVISIONING`.
- TASK-127 status remains the only principal/provenance consumer. The harness
  reads only exact TASK-124 aggregate/report debug labels plus the exact static
  report-entry semantic node after foreground status succeeds. It extracts one
  bounded hierarchy with the TASK-123 DTD/resolver safeguards and never
  persists raw UI.

## Verification

- Complete mocked harness matrix:
  `C:\Program Files (x86)\Microsoft Visual Studio\Shared\Python39_64\python.exe -m unittest tools.tests.test_mobile_staging_acceptance -v`
  - passed: 9 tests.
- Python compile with task-local `PYTHONPYCACHEPREFIX`: passed.
- PowerShell AST parser and `git diff --check`: passed.
- Black/isort: unavailable in the supplied Python environment (`No module named
  black` / `isort`); the test file follows the repository's existing direct
  unittest style, but formatter evidence remains a hosted/reviewer follow-up.

The complete matrix covers old-installed artifact preparation, Owner
Basic gate/resume, stale binding/lock/atomic checkpoint, non-authoritative
stop, broker-unprovisioned stop, crash/unknown resume after grant/restore/logout
with no duplicate mutation, exact mutation result rejection, network `finally`
restoration, API36-style hierarchy transport, static report-entry counts,
non-foreground zero accessibility access, UTF-8 producer-source bindings,
parser, and JSON-redaction fallback exit code.

## Remaining limits

- Basic is repository-composed but has not been run against a device/staging.
- Officer's real path remains intentionally blocked until TASK-128 provisions
  no-disclosure broker plus client/network atomic integration. Broker state and
  network controls are mock-only seams in this repository harness.
- No emulator, staging, network, cloud, Secret, broker, credential, or Owner
  login/consent action ran.

Next actor: Main Work review.
