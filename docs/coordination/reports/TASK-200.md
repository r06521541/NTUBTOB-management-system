# TASK-200 report — unsigned iOS privacy evidence

Base: a8b10c3e9804dc89eb0459917580c02405d3dec3; source/CI integration in progress.

## Delta and interpretation

One read-only stdlib inventory runs after the existing fictional unsigned iOS
archive checks. No extra build, signing controller, dependency, artifact upload
or signed-inspector change. Bounded plist/JSON parsing produces one sanitized
record with safe stage/check/reason on failure; partial facts never become a
complete scan. Missing declarations are not false/empty; resolved SDK versions
are not Dart versions or binary linkage. Duplicate keys/pins, unknown schemas,
native-version conflicts and malformed declaration shape remain findings.

Only exact public aliases and numeric versions are projected; unknown names,
domains, URLs, path/config values and exception strings are not emitted. Source
SHA is associated through the existing CI checkout, not independently attested
by the tool. Metadata/summary hashes are not whole-archive or signature proof.
Quiescent CI input is required; this is not a hostile mutable-filesystem snapshot.

No application/vendor manifest invented. No Apple enum/reason correctness,
Xcode privacy-report generation, complete SDK coverage, runtime behavior, legal
compliance or store-answer claim. Installed TestFlight1.0.0(2) is unchanged.

## Evidence

- Feature RED: missing module/workflow step failed the focused test before
  implementation. Main then added synthetic XML/binary manifests, SPM2/3 pins,
  success/findings/STOP/redaction, file limits/links/change and CI-step contracts.
- `py -3.10 -m unittest tools.tests.test_ios_privacy_inventory
  tools.tests.test_ios_candidate_inspector tools.tests.test_ios_release_pipeline
  tools.tests.test_ci_workflow_contract tools.tests.test_ci_change_classifier -q`:
  90tests,88PASS/2WindowsSKIP (symlink creation permission and bash gate).
- Repository quality format/check for the three owned Python paths and
  compile checks and `git diff --check` pass.33local documentation links resolve;
  PROJECT_STATE remains128lines within its200-line budget. Independent source
  ACCEPT lease2:72PASS/2WindowsSKIP, quality/diffcheck PASS; exact fingerprints
  and constraints are in the existing TASK200 review record.
- Hosted artifact facts are pending the existing unsigned archive job. Local
  Windows fixtures are not macOS/packaged SDK evidence; no real candidate read.

Prior five TASK199 Main-owned closeout files are carried in this substantive
delivery. No unrelated user changes overwritten. No external mutations yet in
TASK200; only the local task branch exists. Existing aggregateUSD20 cap unchanged.
