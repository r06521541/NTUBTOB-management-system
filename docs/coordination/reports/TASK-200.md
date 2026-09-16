# TASK-200 report — unsigned iOS privacy evidence

Base: a8b10c3e9804dc89eb0459917580c02405d3dec3.
Accepted source:0832b7110b390dac444b759e6b04b1c631703e02.
Publication head:139e4cda32b3203050b7f3891fbb00785694b518.
Merge:974ff5ad195057e49c3facd776948990a9c391c2.
Status: completed; PR268 and exact main post-merge CI each16PASS.

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
  Pre-commit PROJECT_STATE was128lines within its200-line budget. Independent source
  ACCEPT lease2:72PASS/2WindowsSKIP, quality/diffcheck PASS; exact fingerprints
  and constraints are in the existing TASK200 review record.
- PR268/run35126415121 unsigned macOS job104896495291 passed. Its actual
  packaged inventory is recorded below. Local Windows fixtures alone are not
  macOS/packaged SDK evidence; no real signed candidate was read.

Prior five TASK199 Main-owned closeout files are carried in this substantive
delivery. No unrelated user changes overwritten. External mutations in TASK200:
Owner-approved task branch push, PR268 creation/squash merge and normal CI; no deployment,
signing/upload or store/provider/Secret changes. Existing aggregateUSD20 cap unchanged.

## Publication gate

Main verified all four accepted LF SHA256 fingerprints against exact Git blobs
in0832b7110b390dac444b759e6b04b1c631703e02, non-main branch and clean tree.
Read-only GitHub metadata confirms public destination
https://github.com/r06521541/NTUBTOB-management-system.git and unchanged remote
main a8b10c3e9804dc89eb0459917580c02405d3dec3.

One guarded push request was rejected by auto-review before process execution:
the existing standing authorization was not accepted as explicit confirmation
of this new public payload. No push, PR or hosted run occurred. Main did not
retry or substitute another tool/destination. No source/test defect was reported.

At that stop, Owner confirmation was requested for the exact15-file code/fictional-test/CI/
native-release/coordination payload (including these acceptance/gate records)
on the same branch/destination, then one normal PR/CI and merge after success.
No private data, credentials, provider values, signing assets or signed artifacts
are in this diff. Frozen implementation hashes remain unchanged. The subsequent
five-file gate-record delta is documentation only; it does not claim CI success,
new authority or a delivered native inventory result.

On2026-09-17 Owner explicitly approved that exact public payload, destination,
normal PR/CI and merge after success. Main rechecked branch/fullSHA/origin,
clean tree and unchanged remote main. Guarded push succeeded once; prior
read-only PR/run lists were empty, then sole ready PR268 was created. No bypass
or duplicate operation. PR run35126415121 completed16PASS including PG15/16,
Android/iOS and CI final gate; `gh run watch --compact --interval45 --exit-status`
exited0. Fresh head/base/check binding was CLEAN and all16SUCCESS. One guarded
squash merge completed without admin bypass. Main verified merge tree equals
the approved publication tree and fast-forwarded local main, preserving owned
evidence edits without reset/stash/force. Post-merge run35127733708 completed
16PASS on exact merge SHA, artifacts0. Structured final lookup confirms
completed/success and no non-successful jobs; no source correction or CI rerun.
Six local final records (HANDOFF, PROJECT_STATE, TASK200 task/report/review,
MOBILE_PRIVACY_DRAFT) await the next substantive PR. No direct-main commit or
standalone status PR. TASK199 closeout is now merged. Main task/advisor leases
are released; installed build2 and all remaining external release gates remain.

## Actual unsigned CI inventory

Run35126415121/job104896495291, inventory step completed successfully. JSON scope
is unsigned_fictional_ci_app, classification INVENTORY_COMPLETE_WITH_FINDINGS,
scan_complete=true, failure=null. Source_commit:
d290d293270c601dd55644bfc85556011d86a084. Read-only GitHub commit metadata confirms
its parents are exact base a8b10c3e9804dc89eb0459917580c02405d3dec3 and approved
head139e4cda32b3203050b7f3891fbb00785694b518. Run artifacts count=0.
Inspected-evidence SHA256:
0b261180400b63f65fcf744165471b45f3c4e63b0be0adb5f0f8d268b9107802.
This hash covers metadata summaries, not the whole app, signed IPA or build2.

Observed13 manifests:12bundles and1framework, all plist-decoded with no known
type-shape findings or unknown keys. All declare tracking=false and empty
tracking_domains. Values/reasons/runtime are not validated.7 manifests retain
unknown_component; an absent LINE alias is therefore not proof LINE lacks a
manifest. Application-root PrivacyInfo.xcprivacy is absent, not a compliance
decision or permission to copy SDK declarations into an application manifest.

| Ordinal | Public alias hint | API entries | Collected-data entries |
| --- | --- | ---: | ---: |
| 1 | app_auth | 0 | 0 |
| 2 | unknown_component | 0 | 0 |
| 3 | flutter_engine | 2 | 0 |
| 4 | gtm_app_auth | 0 | 0 |
| 5 | unknown_component | 1 | 0 |
| 6 | google_sign_in | 1 | 8 |
| 7 | unknown_component | 1 | 0 |
| 8 | unknown_component | 0 | 0 |
| 9 | unknown_component | 1 | 0 |
| 10 | unknown_component | 1 | 1 |
| 11 | unknown_component | 0 | 0 |
| 12 | secure_storage_plugin | 0 | 0 |
| 13 | google_sign_in_plugin | 0 | 0 |

These are declaration-entry counts, not distinct runtime data categories or
proof that App collects none/eight/one. Alias hints do not prove provenance.

Both SPM lock slots parsed, same LF SHA256
e1e955bfd72cc843c5ce9cb217527599a0449851dcbbc5f02bbbc5251e7ab914.
Each has2unknown identities, preserved without raw identity/URL/revision output.
Seven known aliases have equal versions across both slots and no conflicts:
app_auth2.1.0, google_sign_in9.2.0, google_utilities8.1.3, gtm_app_auth5.0.0,
gtm_session_fetcher3.5.0, line_sdk5.17.0, promises2.4.1. Resolution is not linkage;
local plugins/engine and unknowns prevent any complete SDK coverage assertion.

compliance/runtime/sdk_coverage/xcode_privacy_report/signature_verified=false;
upload/release_authorized=false. Next work: identify unknown public dependencies,
review actual first-party required-reason/data-use declarations and later bind
privacy evidence to a reviewed real candidate. No vendor files edited and no
store policy answer submitted. Installed TestFlight1.0.0(2) remains unchanged.

Post-merge run35127733708/job104900884114 also passed the unsigned job. Its
source_commit is exact merge974ff5ad195057e49c3facd776948990a9c391c2; the inspected
summary digest equals the PR's0b261180400b63f65fcf744165471b45f3c4e63b0be0adb5f0f8d268b9107802.
All13manifest facts and7known native versions are unchanged.21inventory tests
ran on macOS with21PASS, including the symlink case skipped on local Windows.

Initial log read was blocked by gh's ANSI-output protection, not a failed CI
job. The same public fictional job log was then captured only in memory using
the documented escape-sequence option; only the unique inventory JSON was parsed
and reserialized. No raw log/ANSI/private values or extra artifact file emitted.

The first main status-watch process exited1 on a transient GitHub API transport
failure. Independent read-only run lookup confirmed the original run continued
and iOS succeeded; Main reattached watch to that same run. No workflow rerun,
merge retry or provider/credential operation followed the transport error.
