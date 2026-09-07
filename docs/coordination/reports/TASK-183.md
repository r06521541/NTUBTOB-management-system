# TASK-183 evidence

Base: `e6fe9b9e7612831cdd5fa75defe9ce022db846e6`; branch: `codex/task-183-ios-cloud-rehearsal`.

## Delta

- Explicit artifact-only IPA inspection preserves actual signature/archive/profile/entitlement checks while removing runtime readiness as an integrity prerequisite. Default TestFlight readiness remains blocked; all modes explicitly deny upload/release authority.
- Regression exposed missing app-level `get-task-allow` rejection (profile already checked). App debugging or malformed values now fail in every mode.
- Fixed, in-memory lifecycle rehearsal covers exact commit, partial staging/build/inspection failures, rejected/uncertain upload, processing pending, cleanup success/failure and no retries. No private reader, live adapter, subprocess, network, signing or upload.
- Existing macOS job runs rehearsal/tests before its unchanged no-codesign compile; Python 3.10 release-tool gate also runs the suite. No workflow permissions, secrets or runner tier changes.
- Runbook records Owner-approved narrow future ephemeral signing design and remaining exact live gates. Apple App ID/capability/record updated as Owner-reported, not live verified.

## Local evidence

- Pre-change new artifact-only regression: 2 expected errors (mode absent / CLI not wired), then implemented.
- Debug entitlement regression initially exposed missing guard; corrected. A malformed fixture used unsupported plist `None`, corrected to a serializable malformed array; not a runtime failure.
- `py -3.10 -m unittest tools.tests.test_ios_candidate_inspector tools.tests.test_ios_release_pipeline tools.tests.test_ios_store_readiness -q`: 37 PASS.
- `py -3.10 -m unittest discover -s tools/tests -p 'test_ci_*.py' -q`: 35 total, 34 PASS, 1 local Bash-dependent skip.
- `py -3.10 -m unittest discover -s tools/tests -p 'test_deploy_*.py' -q`: 89 PASS; expected negative-CLI error text is test output, not failed operations.
- `py -3.10 -m tools.repository_quality check --working-tree`: 4 Python files PASS; pinned format and `git diff --check` PASS.
- Local PyYAML unavailable (`ModuleNotFoundError`); no local YAML-parser claim. Hosted parser/gates must supply final workflow evidence.

## Review / integration

- Independent architecture and final implementation review by `/root/task181_review`: ACCEPT, no blocker; independently ran 37 tests, all PASS plus diff check. Main received and accepted completion; review claim complete.
- Hosted gates, immutable commit, PR and merge pending. This checkpoint does not assert them complete.

## Limits / external mutations

No actual IPA, macOS local signature run, keychain cleanup, Apple upload, device/provider or staging runtime evidence. Fictional cleanup and upload cannot establish those facts. Real bootstrap/live adapter and exact account/credential custody remain later Owner gates. No real secrets read, Apple/GCP/production/paid action; Git/CI integration only when reviewed.
