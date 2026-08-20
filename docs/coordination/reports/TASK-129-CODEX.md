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

## Controlled dogfood correction

- Accepted-main dogfood reached a normal TASK-123 `avd-start=reused` result
  because the exact approved emulator was already running. The harness had
  allowed only `started`, stopped before build/install, and returned a generic
  failure.
- The correction accepts exactly `started|reused`; no other launcher action
  vocabulary was widened. Action-result mismatches now return the bounded
  `ACTION_RESULT_INVALID` reason without the raw result.
- The complete mocked harness suite now passes 10 tests, including an
  already-running AVD and a sentinel invalid-result no-disclosure regression.
  `git diff --check` also passes. No second runtime attempt, build, install,
  login, staging, Secret, database, or cloud action ran during this correction.

- The next dogfood invocation stopped before cleanup/build because stale
  manifest identity was checked only after APK tool invocation. Artifact
  inspection now validates the exact non-secret manifest fields and accepted
  SHA first. Proven stale evidence returns drift; unknown tool outcomes return
  bounded `ARTIFACT_UNAVAILABLE` and are never auto-cleaned.
- Direct regressions prove stale manifest short-circuiting (zero APK tool
  calls) and exception containment with no sentinel disclosure. No runtime
  retry or external action occurred while applying this correction.
- Adjacent review found that root-level evidence purge would collide with the
  live harness checkpoint lock. TASK-123 now exposes only `cleanup-artifact`
  for this path: it removes the exact APK and manifest while preserving the
  TASK-129 checkpoint directory. A direct regression proves that boundary.

## Production dependency closure correction

- Controlled dogfood on merge `6477b90c617b300c47e56dabb93be332ba9febe8`
  stopped before artifact cleanup, build, install, checkpoint creation, or UI
  input. Source-only review found that delayed production scriptblocks did not
  lexically retain the value-free launcher config after their factory returned.
- The production factory now creates explicit lexical closures for action,
  artifact, observation, and checkpoint-policy dependencies. A direct delayed
  invocation regression proves the accepted mode/SHA/config and value-free
  config remain bound without loading any private broker input.
- The same adjacent vocabulary review corrected the harness to accept the
  launcher's exact `signer-check=matched` result instead of the mock-only
  `signer_matched` spelling. The affected complete harness suite passes 12/12.
- No dogfood retry, emulator mutation, build, install, login, Secret, database,
  broker, staging, or cloud operation ran during this correction.

- The next bounded invocation still stopped before cleanup. A read-only direct
  production dependency diagnostic returned only `CommandNotFoundException`:
  TASK-123 commands had also been dot-sourced inside the factory-local scope and
  disappeared when it returned. The factory now loads TASK-123 into an isolated
  in-memory module and captures only its required module-bound ScriptBlocks;
  launcher parameters and commands are not exported into harness/global scope.
  A direct scoped-factory regression proves the bound commands remain callable
  after return. A read-only production diagnostic now returns exact artifact
  state `drift`. No runtime retry occurred for this correction.

- The next dogfood completed the fresh build/sign/install path and stopped on
  `ACTION_RESULT_INVALID` at cold-launch vocabulary. TASK-123 intentionally
  returns `timeout_but_running` when its bounded launcher wait times out but the
  exact portal activity/PID are running; TASK-129 had accepted only `running`.
  The harness now accepts exactly those two terminal-success results without
  retry and continues to reject `timeout_unknown`. A direct regression proves
  the unknown case invokes cold launch only once. A subsequent read-only status
  reached the accessibility stage and failed safely; it was not retried or used
  to claim semantic acceptance.

- After the vocabulary correction, dogfood again completed build/sign/install/
  cold and stopped at semantic observation. A single metadata-only diagnostic
  performed later returned exit zero with bounded output, proving API36
  UIAutomator readiness was transient rather than a persistent configuration
  defect. The harness now retries only the exact read-only accessibility-
  unavailable condition up to three attempts with two-second waits. Unknown
  failures are attempted once and redacted; exhaustion returns bounded
  `EVIDENCE_GAP/STATUS_UNAVAILABLE`. No login or acceptance was claimed.
