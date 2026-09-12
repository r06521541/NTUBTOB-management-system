# TASK-198 report

## Current signing-input classification correction

PR254 merged2ae97b339e542eeea766489dffdcd21aa45cfef6 after CI34698156008
SUCCESS16/16 on9103ba85583eaee20b0f1da0643d3c40369a3411. Accepted tree matched.
Actual ASC_IMPORT_COMPLETE and SETTINGS_READY prove the approved single local copy
and path update completed; originals/other fields retained, no repeated import.
Owner later ran --execute --settings and reported SIGNING_MATERIAL_REJECTED,
run_id=null. Independent metadata checks: zero execution processes, no journal,
no signing workflow runs. Owner uncertain whether CSR/P12 passwords coincide.

Existing intake merged frame and P12/certificate/Team/time/purpose failures into
one reason. Fictional actual P12 probe accepts matching material and rejects
wrong password/certificate/Team; this does not diagnose the Owner's private input.
Main now separates fixed frame/dependency/P12 decode/key/certificate/Team/time/
purpose rejection labels in the same path, with all acceptance conditions intact.
P12_DECODE_REJECTED means parser/decryption failed, not proof of a wrong password.
Unknown errors remain sanitized; no additional CLI, output values, retry, private
cache, signing or upload. 73 focused tests and five-file quality/compile/diff PASS;
full affected suite225tests221PASS4platformskips. Security34 ACCEPT received and
handled with73independentPASS, exact five fingerprints match. Normal hosted CI
and merge remain required; only then a fresh hidden P12 input, no six-field reentry.

## Previous PKCS8 compatibility repair (PR254 merged)

PR253 merged d9d2a4f5f4342891df6d30fea5aaf72ee34d5dfc with CI34696846257
SUCCESS16/16; exact accepted tree verified on clean main. Actual preview returned
ASC_IMPORT_READY, import then KEY_REJECTED before any backup/copy/update. Exact
metadata-only checks independently confirmed backup and destination absent.
Original metadata/key untouched; no signing/upload/runtime or production change.

Main reproduced a parser compatibility defect using only generated fictional
keys: valid P256 PKCS8 with an inner named-curve parameter parses to the same key
but does not reserialize byte-identically. Real input's precise encoding remains
unknown; no direct private inspection or unchanged-code retry. Current branch
codex/task-198-pkcs8-compatibility fixes only bounded receiver interoperability:
four exact encodings regenerated from a crypto-validated key, inner parameter and
public point present/absent; scalar/public consistency checked. Original strict
envelope comparison, P256/type/size and extra-material rejection retained. No
arbitrary ASN.1/BER acceptance or normalization of the copied original key bytes.

Red regression first reproduced refusal; Main218tests214PASS4platformskips and
three-file quality/compile/diff PASS. Security33 ACCEPT,22 independent focused
PASS; copied original bytes/no-repeat and shared ASC/AppleLogin boundaries covered.
Normal CI/merge still required before a fresh preview and one import. No new
Owner fields are needed for this source repair, and the approved copy is still
unperformed. Do not infer ASC key purpose/permissions from format success.

## Previous custody repair (PR253 merged)

PR252 merged b428ab9d25702c0c7516db11e0c20030f09591d6; normal CI34693162874
SUCCESS16/16. Empty protected JSON was created; Owner filled it, SETTINGS_READY
passed, then execution stopped ACL_REJECTED before any signing run/Secret/journal.
Read-only metadata checks isolated the normal inherited-ACL Apple source folder;
fixed signing assets and JSON custody pass. This is not evidence of exfiltration.
Owner approved copying only the JSON-selected ASC key to protected asc-upload.p8,
preserving original files, other five settings and the separate Apple Login key.

Current branch codex/task-198-asc-private-custody, same full base above. Main adds
metadata-only checks for all four upload assets before password and to --check-inputs;
49 focused intake/operator tests PASS. Existing eight settings tests PASS outside
sandbox; sandbox cannot establish the disposable fixture ACL, not a product failure.
Writer17 completed/frozen the single-key copy and settings update. Native fictional
locked-rename experiment failed with sharing violation both inside/outside sandbox;
do not claim atomic replacement or relax sharing. Revised design retains a protected
CREATE_NEW metadata backup before key copy and in-place path update using a single
exclusive settings handle. Partial state stops, preserves backup/key, never retries
or restores automatically. Six fields remain recoverable even if main JSON is torn.

Writer evidence:9 fake and4 Windows native tests PASS (scoped temporary fixtures).
Security30 found completed-copy equality needed private-key revalidation. Main
added red regression then existing ASC parser; Security31 accepted the correction,
10 independent focused PASS, no other findings. Preview still never reads p8.
Main final TestFlight tool regression:215 tests,211PASS,4 existing platform skips;
run with scoped escalation for the native ACL fixture. Six-file quality, compile
and diff check PASS. Six files accepted through Security30/31; normal CI and merge
still required before actual import. No real key payload read/copy, signing/upload,
environment Secret, staging runtime/DB or production mutation in this repair yet.
Subsequent --check-inputs will prove metadata/custody, not crypto/password/ASC scope.
Only the P12 password remains hidden input after saved metadata/custody pass.

PR253 opened at717c603752b56e562ed9d368a89f20e0fa00128d. CI34696504831
Windows native source fixtures failed ACL_REJECTED (3tests); Ubuntu tools and
quality passed. Remaining old jobs cancelled, not a passing run. Main changed
only temporary fixture source/file Owner establishment, preserving inherited DACL
and production code. Security32 ACCEPT, independent4nativePASS; Main full215tests
211PASS4skips. Same PR receives test correction and fresh normalCI, no live import.

## Previous input-recovery repair (PR252 subsequently merged)

PR251 merged48232c548d486c8175ac990dd91d2f68d218544b with normal CI34688813903
SUCCESS16/16. Clean merged-main preflight passed. Protected environment and staging
retained bindings remain verified; existing Owner group now1tester/0builds/manual
distribution. No signed build, upload or device acceptance yet.

Owner reported INPUT_REJECTED after seven hidden inputs. Read-only recovery
confirmed signing-workflow runs0, dedicated environment secrets0 and no journal.
No private values read; safe prompt labels/lengths showed metadata reached final
path input. Owner said quotes were not removed. Fictional tests reproduce quoted
absolute path rejection; this does not prove other supplied values are valid.

Main repairs on codex/task-198-private-input-recovery, base
48232c548d486c8175ac990dd91d2f68d218544b. Delta: one balanced outer double quote
pair on paths; maximum3 syntax attempts per hidden field in current process;
specific allowlisted field/profile/signing-stage errors, never raw values/causes.
No custody/crypto/network/dispatch retry or operation deadline extension.

Owner additionally requested editable JSON to avoid retyping seven inputs.
Fixed local testflight-inputs.json under existing private KnownFolder custody
contains only Team/ASC key/issuer/iOS client/Owner email/ASC path. CREATE_NEW
writes only empty fields with explicit Owner-only ACL; never overwrite.
Bounded same-handle read rechecks metadata/ACL, rejects duplicates/unknown fields,
reports all invalid field names before password/key reads. UTF8 BOM supported.
No password/key bytes/token/approval/target/session field or automatic saving.
JSON reuse never bypasses fresh preflight, target inventory or durable one-shot
journal. Only P12 password is prompted when valid saved metadata is selected.
Former process values cannot be recovered; actual blank template not created yet.

Red tests reproduced original seven failures; source correction then passed:
- py -3.10 -m unittest discover -s tools/tests -p 'test_ios_testflight_*.py' -q
  191 tests,187PASS,4 existing platform skips. Run outside sandbox for native
  temporary fictional ACL test; restricted run could not establish fixture ACL.
- Native Windows test actually creates/edits/reads an empty fictional JSON,
  refuses overwrite and rejects oversized edited metadata.
- py -3.10 -m tools.repository_quality format --paths [six owned Python files]
  passed; final check six Python files and git diff --check also passed.

Security29 ACCEPT received/handled, report_to=/root;47 distinct focused tests
passed, native one separately rerun with scoped escalation after sandbox fixture
setup rejection. Six source/test fingerprints accepted; reviewer completed/read-only.
NormalCI/accepted merge remain next. No real private payload, signing,
upload, environment Secret, staging runtime/DB or production mutation in repair.
Remaining delivery: merged/preflighted JSON + Owner input, actual signing/Apple
processing, Apple staging configuration/schema/backend post-check, Owner-only
distribution and iPhone acceptance. Settings readiness proves syntax, not any
of those outcomes.

## Historical observations / preparation

Follow-up checkpoint171efa870767f2aac161497a402d23869d24176a pushed to PR251.
CI34636351770 found a test fixture portability defect: mocked Windows C:/ paths
were treated as relative POSIX paths in three Ubuntu assertions; Windows passed.
Main corrected only the fixture's PureWindowsPath seam, not runtime validation,
and added four invalid-path cases. Local105tests102PASS3skips; fresh hosted evidence
obtained in run34636911592 SUCCESS16/16; earlier run cancelled/superseded, not PASS.
No private or runtime operation took place. Source3484115c64080679bb58e1eedf6d3df8afc98282
had also passed the earlier code-only run34630386472; it is not the latest checkpoint.

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
