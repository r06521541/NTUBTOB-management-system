# TASK-201 report: Native privacy attribution

Base/head at implementation: 974ff5ad195057e49c3facd776948990a9c391c2.
Branch: codex/task-201-ios-privacy-attribution. Main claim lease1.

## Behavior and evidence

- Added two exact public package identities and six resource bundle aliases,
  with fixed-version upstream sources in MOBILE_PRIVACY_DRAFT. No fuzzy names,
  raw paths or identity output; aliases remain hints, not provenance/linkage.
- Fixed unknown-component classification. Regression initially failed because
  root-present + valid-lock + unknown bundle returned INVENTORY_COMPLETE.
  It now returns WITH_FINDINGS through manifest:UNRECOGNIZED_COMPONENT.
- Generic Resource.bundle remains unknown even nested under LineSDK; no
  manifest-content hash is used to assign ownership. Upstream LINE5.17.0
  manifest content matches TASK200 ordinal10 exactly (982bytes, LF SHA256
  bb1ec69d3627a15a47714e3310aef25af11a27dcf1af4b1b58916823a0e02637).
- Public fictional CI fetch log confirms app-check and Google Interop sources;
  their resolved versions and actual new alias observations are CI-pending.
- Added first-party declaration decision record: linked identity/profile/
  installation/content candidates, limited direct-API inspection, no empty
  root manifest or invented tracking/no-collection policy.

## Local verification

- RED: test_unknown_container_is_a_finding_even_with_root_and_valid_locks
  failed on previous implementation as intended; no unexplained test failure.
- `py -3.10 -m unittest tools.tests.test_ios_privacy_inventory tools.tests.test_ios_candidate_inspector tools.tests.test_ci_workflow_contract -q`
  — 64 tests,62PASS/2WindowsSKIP.
- `py -3.10 -m unittest tools.tests.test_ios_privacy_inventory tools.tests.test_ios_candidate_inspector tools.tests.test_ios_release_pipeline tools.tests.test_ci_workflow_contract tools.tests.test_ci_change_classifier -q`
  — 95 tests,93PASS/2WindowsSKIP (symlink privilege and bash availability).
- `py -3.10 -m tools.repository_quality format --paths tools/ios_privacy_inventory.py tools/tests/test_ios_privacy_inventory.py`
  and same `check` — PASS, owned paths only.
- `py -3.10 -m py_compile tools/ios_privacy_inventory.py tools/tests/test_ios_privacy_inventory.py`
  and `git diff --check` — PASS.
- Local Markdown link check — 21 links,0 missing; PROJECT_STATE140 lines.

No whole local Flutter/backend matrix, candidate signing, SDK runtime validation
or Xcode privacy report claimed. Five new synthetic tests cover aliases,
near-miss redaction, conflict/unknown-version semantics, generic nesting and
root-present unknown classification. Historical TASK200 closeout docs preserved.

## Review / external state

Design ACCEPT proactively received from /root/privacy_foundation lease1.
Source acceptance lease2 ACCEPT proactively received; independent64tests=
62PASS/2WindowsSKIP and quality/diff PASS. No commit/push/PR/CI for TASK201 yet.
External reads: public upstream GitHub sources, Apple official docs and existing
fictional CI job104900884114 log. No private assets or secret values read.
External mutations: none. Local task branch created; source/docs edited.
No new dependency/controller/workflow/job, runtime/deployment/store/Secret change.
App first-party manifest and official policy/store answers await evidence and
Owner decisions; keeping them unresolved is intentional, not compliance PASS.

Reviewer could read fixed-tag sources but could not independently fetch/hash
LINE's public manifest (web cache miss and local connection refused); no bypass
or escalation attempted. Main's successful public GitHub API read plus existing
digest_bytes(text=True) supplies the explicitly limited content correspondence.
Nonblocking document date mismatch corrected; no source correction requested.
