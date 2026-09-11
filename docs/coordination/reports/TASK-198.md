# TASK-198 report

## Current result / required Owner input

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
Apple confirms a separate Sign-in-purpose private key signs developer tokens:
https://developer.apple.com/help/account/capabilities/create-a-sign-in-with-apple-private-key/
Existing .p12/profile/cert presence was confirmed without contents; P12 password
not supplied. No live signing/upload operator implemented yet. Do not repurpose
profile-only intake for keys; finalize reviewed custody and batch missing private
inputs. No secrets in chat or generic CLI; no key regeneration based on uncertainty.

Cost: standard public runner compute USD0; observed7 caches/4161934312 bytes and
zero artifacts. No added paid runner/service/cloud resources or private artifact
upload. USD20 package cap unchanged; cloud/storage cost must be bounded before use.

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
