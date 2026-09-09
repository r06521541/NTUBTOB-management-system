# TASK-190 writer report

## Status and live blocker

Software implementation and focused self-tests delivered for independent review;
**live private execution is not ready or authorized**. Public GitHub Environment
response schema does not guarantee `can_admins_bypass`. Missing/unknown/non-false
value deliberately stops metadata preflight. No live Environment was queried, so
its actual response/protection state is unknown. A subsequent reviewed metadata
readiness gate must resolve this compatibility blocker before any Owner private
read, dispatch or Secret write. Mock acceptance does not establish live usability.

- Branch `codex/task-190-profile-intake`; unchanged HEAD
  `58d90054b52f9c7f5a4788625bd3964ea358c214`.
- Writer `/root/csr_writer`, claim `task-190-writer-20260910`, lease 1. No commit/push.
- Owned dirty paths: `tools/ios_profile_intake.py`,
  `tools/ios_profile_verification_runner.py`, their two `tools/tests/` modules,
  `.github/workflows/ios-profile-verification.yml`, and this report.
  Main owns dependency lock, existing CI/workflow contract, task/HANDOFF/state/runbook.

## Delivered behavior

- Windows default controller: exact clean local/remote SHA, fixed repository,
  main workflow, existing protected Environment, exact Owner reviewer and Secret
  absence metadata checks; no payload reads or mutations. Existing gh credential
  store login is required; token/debug/proxy/config environment overrides are not
  forwarded. Child output is bounded and raw API/exception output is never printed.
- Custody opens only `distribution.cer` and `distribution.mobileprovision` using
  existing Native handle metadata/ACL checks and locked ancestry. No CSR, P12,
  signing key or API key is opened. After exact hidden confirmation, an exclusive
  CREATE_NEW delete-on-close empty local lock enforces local single-writer behavior.
  Team and payload are read/validated only after confirmation, before dispatch.
- Visible action includes one dispatch, one private envelope upload, observation,
  failure cancellation and Secret deletion. This is not two-person control:
  reviewer is Owner `r06521541`, self-review allowed, admin bypass must be false.
  No remote CAS or automatic environment repair is claimed.
- One REST 2026-03-10 dispatch must return HTTP200 and exact run id. Unknown/no-id/
  non-200 result never uploads. Before PUT, exact run identity, main SHA, attempt1,
  waiting Owner deployment approval and current protections/absence are rechecked.
  Environment Secret endpoints use documented `repos/{owner}/{repo}/environments`.
- One versioned <=48 KiB JSON envelope contains only profile/public DER/Team plus
  run id/SHA/nonce and 60-minute validity. Libsodium sealed box is used for GitHub's
  REST transport; this is GitHub custody, not field masking/end-to-end protection.
  No private bytes are sent in arguments, logs, files or artifacts.
- Observe exact named native job for <=45 minutes. Failure may cancel only a
  returned, identity-verified nonterminal run, at most once, with bounded terminal
  reconciliation; `cancel_unresolved` is separate. Unknown ids are never guessed.
  Cancel failure cannot prevent Secret cleanup. Success never cancels.
- Every own PUT attempt gets one DELETE and an independent bounded metadata absence
  check, even after a DELETE exception. PUT/DELETE uncertainty remains
  `retention_unresolved` even when a following read says absent. HTTP204 PUT is not
  accepted as new creation; DELETE404 remains ambiguous. No dispatch/PUT/DELETE or
  force-cancel retries. Before-PUT failure never deletes another possible Secret.
- Process death may retain Secret; expiry blocks verification but does not delete.
  Deleting Secret cannot erase runner memory already received. Owner retains manual
  reconciliation responsibility. Failure output separately reports confirmed Secret
  absence when it is genuinely known, without implying successful verification.

## Runner and workflow

- Manual-only `ios-profile-verification.yml`, fixed repo/main/SHA/attempt gate,
  protected Environment, standard ARM64 `macos-15`, pinned actions/Python3.10,
  hash-locked wheel dependencies, contents read-only, checkout credentials disabled.
- `--prepare` installs no private environment: checks context/source SHA, compiles
  existing production CMS helper and copies only public code to a fixed private-mode
  runner temporary directory. A bound hash/identity receipt guards subsequent use.
- Only the `--verify` step receives Secret. It removes the variable before native
  invocation, enforces exact envelope/run/SHA/ref/nonce/time plus local consumption
  guard, reuses fixed-production CMS and TASK187 content checks. No trust override.
- `--cleanup` always removes only fixed public code/receipt/consumption files;
  unexpected entries/symlinks stop. No private file artifacts, caches, keychains,
  runner PAT, signing or app upload. All release authority flags stay false.
- `python -m tools.ios_profile_verification_runner --rehearsal` checks fictional
  positive native/content binding in its separate test build, then actual production
  prepare -> verify fictional envelope (must reject trust) -> cleanup with absence
  assertion. It does not grant production verification from a fictional root.

## Evidence and limits

- Writer focused suites: 20 run, 19 PASS, 1 explicit macOS native skip on Windows.
  Scoped escalation was used solely for disposable fictional Windows ACL/lock
  fixture: same-handle read, second-lock refusal, rename denial, delete-on-close
  cleanup and proof that no private packaging input exists were PASS.
- Later bounded focused checks for unconditional DELETE reconciliation, separate
  cancellation/absence results and one-cancel uncertainty were PASS.
- Owned four Python files: repository_quality format/check PASS; git diff --check PASS.
- Main separately reports 127 affected tests OK, 4 skips under scoped fixture
  escalation. Main's sandbox ACL setup failure was environment-only; writer's native
  fixture passed outside sandbox. No production guard was relaxed.
- Swift/native runner phases cannot run on local Windows. Mandatory hosted macOS
  rehearsal and independent review remain required. No real profile/certificate,
  Environment, workflow dispatch/approval, Secret or live result has been inspected.
- External mutations: none. Only repository owned files and automatically cleaned
  fictional/public-code temporary fixtures were written. No real private assets,
  GitHub requests/mutations, cloud/store, commits or pushes occurred.

References: [GitHub workflow dispatch API](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event),
[Environment Secrets API](https://docs.github.com/en/rest/actions/secrets),
[Environment API](https://docs.github.com/en/rest/deployments/environments).
