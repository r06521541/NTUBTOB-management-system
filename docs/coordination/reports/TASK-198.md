# TASK-198 report

## Current result (supersedes historical observations below)

Continuing Draft PR251, branch codex/task-198-owner-testflight; main/base remains
5762a89c6e6451ed19f5151da1652312a9f76679. Exact pushed source
3484115c64080679bb58e1eedf6d3df8afc98282 passed run34630386472,16/16 jobs SUCCESS,
including actual Swift compile/invalid-input rejection and unsigned iOS archive.
This proves code-only platform compatibility, not real Keychain/import/signing.
The earlier run34629242446 completed with14 PASS and two dependent failures.

Further source now includes Windows custody/intake, bounded wire/dispatch,
SPM-aware preparation, manual signing, independent IPA inspection, separate ASC
upload/processing and hosted phase orchestration. Main focused discovery:
py -3.10 -m unittest discover -s tools/tests -p "test_ios_testflight_*.py" -q:
102 run,99 PASS,3 POSIX/native skips. Working-tree quality16 Python PASS; diff PASS.
These new sources are not yet hosted-validated, merged or live-executed. Review20
accepted the retention correction but found missing private upload-receipt handoff.
Main made both the workflow and hosted live entry explicitly disabled, and refuses
cleanup of any known remote receipt. Review21 ACCEPT covers dormant-source safety only.
Final Main discovery104tests101PASS3skips and18workflow-contract tests17PASS1skip.
Real execution stays prohibited until durable private receipt/journal handoff exists;
no claim that retaining a file on an ephemeral runner alone solves the handoff.

Independent accepted slices: upload12, inspection14, intake15, wire16, runner17,
SPM correction18. Security19 required separate current absence from retention
resolution after uncertain secret writes/deletes; Main corrected the output and
added PUT/DELETE timeout cases, now11 dispatch tests PASS. HTTP uncertainty remains
sticky and prohibits a successful retention/overall result even after current404.

Named next Owner gate: create/configure NEW GitHub ios-owner-testflight environment
through visible settings with Owner required reviewer, self-review allowed, no
admin bypass, exactly main branch and no tags. Do not alter profile-verification.
Official REST write schema does not document admin-bypass control; no undocumented
PUT or weaker bootstrap was implemented. A fresh GET of the existing old environment
does return can_admins_bypass=false, so strict readback is available after UI setup.
No environment, secret, signing/upload, staging/runtime/DB or production mutation.

Still incomplete beyond this source checkpoint: complete Windows session/journal
operator; actual private custody/password/key input; exact ASC Owner group/tester
setup and sole-group distribution; staging Apple configuration/migration/deploy;
real signing/upload/Apple processing and Owner device acceptance. Do not dispatch
the new workflow or merge this partial delivery as release-ready. No new credentials,
certificates, public release or extra testers requested. Incremental cost unchanged.

## Historical observations / preparation

Follow-up checkpoint171efa870767f2aac161497a402d23869d24176a pushed to PR251.
CI34636351770 found a test fixture portability defect: mocked Windows C:/ paths
were treated as relative POSIX paths in three Ubuntu assertions; Windows passed.
Main corrected only the fixture's PureWindowsPath seam, not runtime validation,
and added four invalid-path cases. Local105tests102PASS3skips; fresh hosted evidence
required, earlier run is not PASS. No private or runtime operation took place.

PR250 merged `5762a89c6e6451ed19f5151da1652312a9f76679`; Git rev-parse verified.
Reviewed source `8066ea54fbe4fd53bf01b06d46756550271cef57`, run34618189006 completed
SUCCESS,16/16 jobs PASS including both PostgreSQL versions, Android and iOS archive.
Native diagnostic35 tests PASS, SELECTION_DIAGNOSTIC_COMPLETE, cleanup VERIFIED,
codesign NOT_RUN. No fake signing/real-signing claim. Watch process closed.
Squash and reviewed source share tree2eb7e7893574fd4621e1e2db08ecfa46a692e270;
automatic duplicate main run34619125140 completed/cancelled confirmed, not another
PASS. No active run or local watcher remains; closeout date2026-09-12 Asia/Taipei.
New local branch codex/task-198-owner-testflight starts at merged SHA; local
closeout records retained for next substantive commit, no status-only push.

Owner completed login2026-09-12. Authenticated Apple/ASC read-only inventory:
- Existing explicit App ID tw.org.ntubtob.portal; Sign in with Apple enabled as
  primary App ID. No form changed; Save disabled; exited without save.
- Developer Keys page shows Getting Started with Keys, no existing key rows.
- One Distribution certificate and one iOS App Store profile listed, expiry2027-09-09.
  Metadata only, not private-key matching, profile trust or signing readiness.
- ASC NTUBTOB App exists; TestFlight has no builds, no listed internal groups and
  zero testers. Recheck exact relationships/automatic distribution before upload.
- One active ASC team upload key with Developer role exists. No payload read or
  download; local possession/key pairing and effective operation rights unverified.
- No Apple/GCP/DB mutation, key creation/revocation, download, signing or upload.
No personal/account/key identifiers copied into durable records. These categories
record observation, not substitute for reviewed execution target binding/preflight.

Owner explicitly approved the ONE App-bound Sign-in-purpose key on2026-09-12.
Main rechecked empty Keys list and prepared the visible draft only: approved name,
only Sign in with Apple enabled, sole existing primary App selected. Final Register
summary verified; Register not clicked, no key downloaded or payload read by agent.
Owner subsequently reported downloaded. Main observed Download Your Key, disabled
Downloaded control with the approved name and Services: Sign in with Apple.
Registration/download confirmed by portal state and Owner; no duplicate request.
Local file location/custody/key pairing remain unverified; no payload read. Existing
certificate/profile/ASC upload key unchanged. Main resumed source preparation;
Private-input writer lease2 completed/frozen; architecture lease3 ACCEPT handled.
Two new source paths: tools/ios_testflight_inputs.py and
tools/tests/test_ios_testflight_inputs.py. Writer29 focused fictional tests PASS;
bounded memory-only P12/certificate/profile matching and separate ASC/Apple keys,
ES256 tokens with fixed10-minute ASC and7-day Apple service-credential expiry.
No trust claim, reader, native call, live controller or private input. Independent
source security review lease4 ACCEPT received/handled;9 new focused tests PASS.
Main quality check for both paths and diff check PASS; canonical LF digests match
review. Both agents completed/read-only. This is a branch work-package checkpoint,
not a new PR, hosted CI, real signing or release. Current branch remains
codex/task-198-owner-testflight based on the merged SHA above.
Main repeated py -3.10 -m unittest tools.tests.test_ios_testflight_inputs
tools.tests.test_ios_profile_validation tools.tests.test_ios_certificate_packaging
-q:29 PASS, no skip. Hosted/native/private execution not run for this source slice.

Read-only Google Console inventory could not access the primary project with the
current signed-in account. iOS Google client remains UNKNOWN; no IAM/OAuth
mutation. Account selection opened for the Owner's existing authorized account;
login/MFA is a necessary user step, not a request to grant more permissions.
Owner subsequently reported login completed. Main verified authenticated access
to ntubtob-schedule-405614 and its OAuth client list: exactly one Android and one
Web entry, no iOS entry; no filter or pagination shown. This supersedes UNKNOWN
for this visible list only. No client detail/secret download, clipboard, form-field,
IAM or provider mutation. Source contract and official Google documentation
require a distinct iOS-type client. Main proposes one additive iOS client, pending
Owner consent; no creation action taken and no new agents/hosted runs dispatched.
Owner subsequently approved this exact one-client proposal. Main rechecked the
unchanged two-client list, opened the new-client form and populated only iOS type,
approved name and bundle. Optional App Store/Team fields remain empty and App
Check remains unchecked/disabled. Create enabled; Main did not submit. The visible
manual action is ready for Owner under COLLABORATION8; no additional approval
phrase, key download, IAM or existing-provider update requested.
Owner reported completion; Main observed OAuth client created success dialog,
then exactly one iOS plus previous Android/Web rows. New-client detail matched
approved name and tw.org.ntubtob.portal; optional App Store/Team fields blank.
Exited with Cancel without editing/saving. Owner create_count=1, agent create_count=0;
no duplicate/download/clipboard or raw identifier in durable records. Provider
propagation and actual sign-in remain untested. Writer lease3 and security advisor
lease5 now assigned for genuine signing adapter and private transport integration.
Apple confirms a separate Sign-in-purpose private key signs developer tokens:
https://developer.apple.com/help/account/capabilities/create-a-sign-in-with-apple-private-key/
Existing .p12/profile/cert presence was confirmed without contents; P12 password
not supplied. No live signing/upload operator implemented yet. Do not repurpose
profile-only intake for keys; finalize reviewed custody and batch missing private
inputs. No secrets in chat or generic CLI; no key regeneration based on uncertainty.

Cost: standard public runner compute USD0; observed7 caches/4161934312 bytes and
zero artifacts. No added paid runner/service/cloud resources or private artifact
upload. USD20 package cap unchanged; cloud/storage cost must be bounded before use.

Actual signing-adapter source plus code-only hosted compile/input rejection added;
independent source reviews6/7 ACCEPT, Main source digests matched. Local combined
29 tests27PASS/2platform skips; three changed Python files quality PASS. Windows
does not compile Swift or prove native cleanup. Pre-live filename/Keychain idle
locking corrections are being implemented by writer lease4 before final review.
Those corrections now completed and independently ACCEPTED under security lease8;
13 focused PASS, Main combined41 tests39PASS/2platform skips, quality/diff PASS.
Windows byte/hash-copy tests mock POSIX metadata validation; no real race/native
cleanup coverage claim. Four new source/tests + workflow + five coordination
paths form the next substantive checkpoint; native test remains platform pending.
No real credentials, new environment, hosted run, signing, upload or runtime
mutation for this slice yet. A single early Draft PR is justified only to obtain
missing macOS evidence; it remains the continuing delivery, not another closeout.

Read-only public Apple OpenAPI4.4.1 inspection confirms Build Upload REST uses
buildUploads -> buildUploadFiles -> bounded Apple-provided upload operations ->
file PATCH uploaded=true with sourceFileChecksums (plural), then separate build
processing verification. Uploaded COMPLETE is not device or distribution success.
BetaGroup hasAccessToAllBuilds must be checked across all app groups before upload;
only the exact Owner group/tester may gain access. API/private inputs untested.
Official asset-upload guidance says storage operations do not use ASC JWT; URLs
remain private. Build Upload schema, not screenshot-specific checksum fields,
must govern the future adapter. No signed URL, account ID or payload persisted.
https://developer.apple.com/app-store-connect/api/
https://developer.apple.com/documentation/appstoreconnectapi/build-uploads
https://developer.apple.com/documentation/appstoreconnectapi/uploading-assets-to-app-store-connect

Signing checkpoint b0f60ac60f8e6fae99fb186931134ec23762f272 pushed; Draft PR251
created as the continuing delivery. Run34629242446 compiled the actual Swift
supervisor and failed before material intake; first4096-byte diagnostics retained
only deprecation warnings, not the compiler error. Main found a separate
source-directed Darwin nullable spawn-handle correction using Swift Foundation's
Darwin implementation, and bounded diagnostics now prioritize error lines.
Independent security lease9 ACCEPT,2 focused tests PASS; Main16 tests15PASS/1skip,
quality/diff PASS. Actual compiler success/unique root cause remains unproven.
Other finished jobs passed, including unsigned iOS archive and both PostgreSQL
versions; Android job still active at this observation. No real material/run
custody, signing/upload, protected-environment creation or runtime operation.
Upload writer lease5 works only its two separate new source/test paths.
First run now completed:14 jobs PASS including Android; only native compile and
dependent final gate FAIL. Main pushes reviewed source correction, preserving
the untracked upload work and continuing the same Draft PR without merge.

## Preparation history

IOS-TF-01 accepted 2026-09-11. Start HEAD
3b1be6a607c565fa4184aec3493ef527995fbf19; same Draft PR250.
Five prior Main TASK197 closeout records preserved. Execution begins with source,
cost and capability preflight; no real key/Secret use or external mutation yet.
Incremental cost: USD0 incurred by this package so far; no paid run dispatched.
Sign/upload/private-input availability and staging readiness remain unverified.

Read-only discovery: repository public, main unchanged, existing protected profile
verification environment retains reviewer/main branch rules. Standard ubuntu/windows/
macos-15 runner compute is USD0 for public repos per GitHub documentation; no new
artifact/cache storage or paid runner requested in this package.
https://docs.github.com/en/actions/reference/runners/github-hosted-runners
Private-directory metadata only: distribution.p12, distribution.mobileprovision and
distribution.cer present. No payload read or validity claim; password not supplied.
Exact staging service mobile-api-staging in ntubtob-mobile-staging/asia-east1 Ready.
All four MOBILE_API_APPLE_* configuration keys absent by name-only projection;
no env values/Secret payload/DB read, no mutation. Schema remains unverified live.
Two advisors completed; architecture supported Xcode manual signed archive/export.
First source slice retires intentional diagnostic CI failure without claiming actual
signing or changing public readiness. Real operator not yet implemented; missing
P12 password and authenticated ASC/Apple/staging private input are pending gates.

First source slice completed: successful no-sign selection diagnostic no longer
forces CI failure; underlying nonzero failures remain. Checklist separates artifact
integrity and internal scope/custody from later device/public release. No live
signing controller or readiness-marker mutation. Writer and independent reviewer
each28 tests27PASS1skip; Main repeated same and quality PASS. Source ready to push
existing DraftPR250; selected hosted CI must pass before merge.
Accessible browser had no Apple authenticated tab; developer.apple.com/account
opened to Apple login. Owner login/MFA requested, tab handed off; no credentials
entered or key created. Owner uncertain about Sign-in-purpose key; do not infer
absence or reuse ASC upload key for Apple login. Private execution paused on this
named input gate while independent source integration completes.
