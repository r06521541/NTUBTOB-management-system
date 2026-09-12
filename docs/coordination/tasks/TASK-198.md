## Current ASC preflight correction

PR255 merged9fb467ea37b7f2e2b4c5f06a48d8570d7a8997b7 after CI34702831760
SUCCESS16/16. Owner then reported OPERATION_UNRESOLVED after the P12 prompt.
Read-only checks found no journal, signing run or six temporary transfer Secrets.
Fictional reproduction proves OWNER_SCOPE_REJECTED is masked by the operator;
actual failing stage remains unknown. Browser corroborates the existing internal
Owner-only group/manual distribution and active Developer upload key; browser
observations do not authorize dispatch or replace API preflight evidence.

Goal: check ASC before requesting P12; one bounded GET-only layer split.
Core: tools/ios_testflight_operator.py, tools/ios_testflight_owner.py, direct tests.
Invariant: no relaxed group/trust/ACL checks, password cache, raw errors or retry;
normal execution still freshly collects materials/rechecks scope before dispatch.
Tests: fictional GET success/auth/permission/transport/scope failures, fixed stage
output, no P12/profile/Login-key reads or prompt/mutation in --check-asc mode.
Unknown: actual API response; one reviewed --check-asc using saved six-field JSON
and its protected ASC key is authorized by IOS-TF-01. No live execute this slice.

Main task-198-main-20260911 lease1 owns four Python paths and existing records;
branch codex/task-198-asc-preflight, base=head
9fb467ea37b7f2e2b4c5f06a48d8570d7a8997b7. Security35 review follows frozen source.
Runtime: operator=agent; owner_gate=none for GET-only check; authorization=IOS-TF-01;
report_to=/root; stop on private input/new key/access expansion, unclear mutation
or inconclusive repeated diagnosis. Do not rerun signing or request another P12
password to obtain diagnostics. Store only fixed sanitized final classification
and stage, never key/identifier/contact/response values.

Security35 packet: task=TASK-198; branch=codex/task-198-asc-preflight;
base=head=9fb467ea37b7f2e2b4c5f06a48d8570d7a8997b7;
actor_id=/root/task181_review; role=advisor; claim_id=task-198-security-20260911;
lease_version=35; write=read-only; owned_paths=none; report_to=/root.
Scope: four frozen Python paths named above and this bounded GET-only entry;
check no signing/P12 read/prompt/dispatch in --check-asc, unchanged trust/group
predicates and fresh rechecks in normal execution, no raw errors/values or retries.
Stop on drift, private input need or scope conflict. COLLABORATION2 mandatory
ACK/heartbeat/blocker/proactive final applies. Main stays active running full
affected tests; no real ASC key use until accepted commit/CI/merge.

Security35 REQUEST_CHANGES handled: fix three fake custody tests' Windows path
semantics on POSIX CI, not production path validation. Main applies PureWindowsPath
seam like existing intake fixtures; no source changes. Revoke lease35; activate
Security36, same actor/role/branch/base/head/report_to and mandatory protocol;
scope only this test delta plus unchanged previously reviewed source fingerprints.
Main reruns affected tests while reviewer independently checks portability.

## Previous signing-input classification correction

PR254 merged2ae97b339e542eeea766489dffdcd21aa45cfef6 after source
9103ba85583eaee20b0f1da0643d3c40369a3411 passed CI34698156008,16/16.
Actual reviewed import returned ASC_IMPORT_COMPLETE, then SETTINGS_READY;
the approved single ASC copy/path update is complete and must not be repeated.
Owner subsequently entered the hidden P12 password; local execution returned
SIGNING_MATERIAL_REJECTED, run_id=null. Independent read-only checks found zero
matching execution processes, no operation journal and zero signing workflow runs.
Owner is unsure whether CSR/P12 passwords were the same. No password is available
to Main and no actual private input will be reread during this correction.

Goal: identify the rejecting stage in the existing intake, not create another
diagnostic CLI or guess that the password is wrong.
Core: tools/ios_testflight_signing.py, tools/ios_testflight_intake.py, their direct
tests and operator propagation tests, plus existing coordination records.
Invariant: all existing key/certificate/Team/date/purpose checks, custody, one-shot
and no-retry behavior unchanged; only fixed reason codes, never values/exceptions.
Tests: real fictional encrypted P12 positive/negative bindings, frame separation,
private-sentinel suppression, no repeated prompt and zero dispatch on rejection.
Unknown: actual frame versus decryption/key/certificate failure; no claim of a
material repair. Fresh hidden password still required after reviewed CI/merge.

Main claim task-198-main-20260911 lease1 owns those five Python paths and records.
Branch codex/task-198-signing-input-reasons; base=head
2ae97b339e542eeea766489dffdcd21aa45cfef6. Prior writer/reviewer completed/read-only;
independent Security34 review will follow frozen source before commit/CI.

Security34 packet: task=TASK-198; branch=codex/task-198-signing-input-reasons;
base=head=2ae97b339e542eeea766489dffdcd21aa45cfef6;
actor_id=/root/task181_review; role=advisor; claim_id=task-198-security-20260911;
lease_version=34; write=read-only; owned_paths=none; report_to=/root.
Scope: five frozen Python paths above, fixed local signing rejection stages only;
verify identical acceptance predicates, no raw/private exception propagation,
no repeated prompt/dispatch, actual fictional encrypted P12 coverage. Stop on
source drift, private input need or scope conflict. COLLABORATION2 mandatory
packet protocol applies: immediate ACK, heartbeat, blocker and proactive final.
Main remains active, concurrently runs full local affected tools; no live retry.

# TASK-198: deliver Owner-only iOS TestFlight candidate

Type delivery; delivery_group ios-tf-01; L3. Owner approved IOS-TF-01 on
2026-09-11 and requested immediate execution until acceptance or a named stop.
Use existing branch codex/task-197-fictional-signing and Draft PR250 as the
single continuing release delivery; do not create a second competing PR.
Base bf7430023825ddbf0160515a02b1c24b8a653749;
start HEAD3b1be6a607c565fa4184aec3493ef527995fbf19.
Preserve five carried Main TASK197 closeout records; no other initial dirty paths.
TASK197 observation is complete, not fictional signing success.

## Owner authority IOS-TF-01

Outcome: NTUBTOB, existing bundle identity, staging:real/Release/Basic only,
Owner-only TestFlight availability, then real-device core acceptance with Owner.
Authority includes repository/workflow/tool fixes, independent review, tests,
branch/commit/push/PR/merge; controlled use of existing signing/API assets;
signed archive/IPA validation; necessary staging Apple configuration, dedicated
Secret bindings, backend deployment and compatible migration with rollback;
exact App capability/profile correction; Apple upload/processing queries and
manual distribution only to Owner in a dedicated internal group.
No automatic distribution to other groups or testers. Source merge is not release.

Supersedes TASK197 one-observation/no-retry restriction and per-SHA manual approval
ONLY within this package. Main records exact target/action/count/source/artifact,
read-only preflight, scope match, independent review and execution result. This
standing approval permits each reviewed in-scope operation without another Owner
phrase. Keep one operation per execution, idempotency and ambiguity handling:
pre-execution rejection or confirmed-zero may be corrected; successful operations
are not resent; uncertain results require read-only reconciliation, no blind retry.
After two rounds without useful new evidence, internally reassess the architecture.
Xcode-led delivery may replace redundant custom/fictitious gates, but no fake PASS,
weakened authentication, trust-all, unrestricted key ACL or erased evidence.
Device acceptance follows a distributable internal candidate, not before upload;
unverified device/provider scenarios stay explicit and are not production claims.

New incremental CI/cloud cost cap USD20 for entire package; no new paid service or
plan upgrade. Before chargeable work establish an observable conservative cost
bound and maintain aggregate reservation/spend evidence; unknown/excess cost stops.
Credentials only through reviewed repository tools/private approved custody; no
chat/Git/command-line/raw logs. Separate signing/upload custody; temporary cleanup
required. IPA only in verified private storage, never default public CI artifacts.

Stops: required private input/login/MFA/consent/terms or Owner device action;
new/revoked/rotated signing certificate, replacement App, unrelated/shared production
provider change; exceeded/unknown cost or new resources beyond scope; security
incident/unresolved cleanup/external uncertainty; any production/real-team-data
mutation; non-Owner tester invitation, external Beta Review or public release.
No production, shared Google/LINE production callback change, push/crash upload,
legal/retention policy decision or irreversible real deletion. Privacy/deletion
preparation may proceed in code/fictional tests, not real data mutation.

## Execution checkpoint

Goal: usable first internal candidate, not another standalone diagnostic round.
Core: existing iOS controller/native/workflow/inspector, Apple staging runtime,
release checklist and this task's coordination records; exact writer paths later.
Invariant: isolated staging, Owner-only distribution, least-privilege existing
assets, bounded cost/private custody; platform acceptance never inferred.
Tests: affected security suites/negative cases, independent review, scoped macOS
evidence, exact artifact/runtime post-check, then Owner iPhone core matrix.
Unknown: safe signing route, available opaque inputs, cost visibility and exact
staging/Apple resource readiness; read-only preflight first.

## Active claims

Main /root; task-198-main-20260911 lease1; role main-work; report_to=/root.
Main owns coordination plus integration after scoped writer claims. Prior TASK197
writer/reviewer leases completed and revoked for new work.

Advisor /root/task181_review; task-198-security-20260911 lease1; read-only;
owned_paths=none; report_to=/root. Review supported Xcode-led real signing/custody
architecture against existing code and public primary sources. Identify smallest
safe complete route, exact exposure/verification, not more fake identity research.
No private/network mutation/CI/source edits. Main concurrently audits access/cost.

Advisor /root/csr_writer; task-198-readiness-20260911 lease1; read-only;
owned_paths=none; report_to=/root. Inventory current repository iOS configuration,
staging/provider/readiness marker and existing operator/private input contracts;
identify concrete missing inputs/operations and circular gates, no private files,
cloud/store calls or edits. Main handles external read-only checks.

Both packets use this exact branch/base/head and COLLABORATION2 mandatory protocol:
ACK received/executing with report_to=/root, heartbeat10-15min, blocker immediate,
proactive completion with full HEAD/dirty paths/tests/findings/limits/mutations.
Main stays active, handles packets and explicitly assigns subsequent writer role.

## First implementation slice

Both advisory leases completed; Main received/handled reports. Architecture ACCEPT:
reviewed Xcode manual signed archive then manual export; prepare dependencies first,
but explicitly allow reviewed Flutter/Xcode/plugin build phases in the key window.
No claim the old no-code-after-key rehearsal invariant still describes real signing.
Key access remains scoped, no automatic provisioning/new certificate/global ACL.
Private signing and ASC upload custody remain separate; missing actual inputs block
real execution, not source preparation. Existing profile-only intake is not reused
as an unreviewed private-key transport. No claim its environment accepts new keys.

Revoke readiness advisor lease1. Activate /root/csr_writer as codex-writer,
task-198-writer-20260911 lease1, report_to=/root; same base/branch/start HEAD.
Owned paths: .github/workflows/flutter-tests.yml,
tools/tests/test_ci_workflow_contract.py, docs/releases/IOS_TESTFLIGHT_CHECKLIST.md.
Slice removes the obsolete intentional failure after a successful no-sign diagnostic.
Keep diagnostic validation/nonzero failures, existing tests/archive and no-sign
claims; no true signing/public-ready marker changes. Update checklist to distinguish
reviewed artifact-only inspection/internal upload from later device/public acceptance,
and explain IOS-TF-01 scope. Tests first; focused CI contract and iOS pipeline tests.
No private/native/Git/API mutation by writer. Main owns coordination and architecture
report; security reviewer follows source handoff before any commit/hosted gate.
This slice is a boundary correction, NOT a live signing controller or TF success.

Writer lease1 complete/read-only;28 focused tests27PASS1skip, quality/diff PASS.
Activate task-198-security-20260911 lease2, /root/task181_review advisor/read-only,
owned_paths=none/report_to=/root; review three writer paths plus Main DEC-109,
COLLABORATION scoped exception, TASK198/HANDOFF/report/review and state correction.
Same branch/base/start HEAD and all dirty paths; verify no weakened true evidence,
Owner scope faithfully represented, old TASK197 evidence not relabeled. No native,
private/Git/API/CI mutation. Main audits authenticated platform availability while
review proceeds; private-input stops still apply before real signing/config.

Security lease2 ACCEPT handled; Main28 tests27PASS1skip/quality PASS. Both agents
completed read-only. Commit current substantive boundary correction on shared branch,
run normal selected CI (standard public compute), merge existing PR250 only after
green/no unresolved code findings; do not equate merge with real signing/TF.
Apple account tab reached login, Owner login/MFA required and requested. Keep real
operations paused pending authenticated target inventory and reviewed live custody;
source integration may finish independently. No secret payload or Apple key read.

First slice merged via PR250 at5762a89c6e6451ed19f5151da1652312a9f76679 after
run34618189006 on8066ea54fbe4fd53bf01b06d46756550271cef57 passed16/16 jobs.
Old branch's delivery complete; no new PR yet. Remaining IOS-TF-01 moves to
codex/task-198-owner-testflight from merged SHA, Main lease1 retained; new writer
claim must use that branch/base/HEAD. No live controller implemented or released.
Owner completed Apple login on2026-09-12; Main verified authenticated Apple/ASC
read-only inventory. Existing App/capability, certificate/profile and ASC upload
key retained. Developer Sign-in-purpose Keys list empty; no key created/downloaded.
Owner explicitly approved on2026-09-12 creation of ONE key named
NTUBTOB Staging Apple Login, Sign in with Apple ONLY, primary App ID
tw.org.ntubtob.portal, used only by isolated staging in IOS-TF-01. No certificate
replacement, other capabilities, production use or existing-key revocation.
This is action-time approval for that ONE persistent-access key, not other keys.
Private download/custody remains required; never paste a secret into chat.
Manual Console packet per COLLABORATION8: operator=owner; owner_gate=manual_key_creation;
standing_authorization=IOS-TF-01 plus2026-09-12 exact one-key consent;
report_to=/root; stop_only_on=target-or-scope-drift|unexpected-terms|uncertain-result.
Main may prepare the visible new-key draft with only the approved name/service and
existing primary App selection; final Register and private download belong to Owner,
not an unreviewed scripted operator. No new signing/upload wrapper claimed.
Owner clicks Register once, downloads the resulting p8 privately outside repository
and cloud-synced folders, and reports only downloaded. No payload/key identifier
needed in chat. If interrupted/uncertain, inspect existing Keys before another
Register; never create a duplicate or revoke to repair a download uncertainty.
Then finalize reviewed live custody/controller and batch remaining private input.
Existing files/portal metadata do not prove payload validity or signing readiness.

## Live input and runner preparation

Owner reported downloaded2026-09-12; Main observed Download Your Key with disabled
Downloaded control and only Sign in with Apple. No repeat registration/download;
actual local key custody remains unverified. Source preparation resumes without
requesting secret input before the complete reviewed operator is ready.

Revoke completed writer lease1 and security lease2 for new work. All packets use
branch=codex/task-198-owner-testflight;
base=head=5762a89c6e6451ed19f5151da1652312a9f76679; report_to=/root;
COLLABORATION2 ACK/heartbeat/blocker/proactive full-SHA completion applies.
Initial dirty paths are the five existing Main TASK198 coordination records only.

Writer /root/csr_writer; task-198-writer-20260911 lease2; role=codex-writer;
write=allowed; owned_paths=tools/ios_testflight_inputs.py,
tools/tests/test_ios_testflight_inputs.py. Bounded work package: implement reusable
local private-input validation and separated in-memory signing/upload/Apple-login
material types for the forthcoming real operator, plus offline fictional tests.
Reuse reviewed Windows handle/ACL/path primitives and pinned cryptography rather
than another custom CMS gate. Validate P12 private-key/certificate association,
certificate distribution purpose/validity/team, exact bundle/profile structural
binding without asserting Apple trust, distinct P256 API/provider keys and signed
short-lived ASC/Apple JWT construction. Private paths/password through hidden input
only when invoked by the future controller; no generic standalone live CLI, export,
secret persistence, network, Git/cloud/store/native mutation or true ready claims.
Public constants/signatures and bounded fixed error categories; no repr/traceback
of private inputs. Main handles integration; writer self-review/tests before handoff.
Stop on out-of-scope input need, unsafe custody primitive or substantive mismatch.

Advisor /root/task181_review; task-198-security-20260911 lease3; role=advisor;
write=read-only; owned_paths=none. Resolve one concrete real-runner architecture:
manual signed archive/export on ephemeral standard macos-15 runner, memory P12
import with named-tools ACL, Xcode identity/profile discovery, key cleanup before
separate ASC upload, no public artifact/logs. Examine whether exact export can work
without search-list changes; if not, assess narrowly scoped ephemeral-user change
plus verified restoration (never a global login-keychain or trust-all workaround).
Return supported commands, minimal helper changes and precise boundary decision,
not another fictional-signing round. No private material or external mutation.
Main concurrently audits workflow/staging input/dependency/cost contracts.

Security advisor lease3 ACCEPT received/handled. IOS-TF-01 supported-runner decision:
replace the prior absolute no-search-list-change constraint ONLY for a single-use
standard GitHub-hosted macos-15 VM. Native supervisor snapshots user search-list
and default, inserts exactly its own temporary Keychain preserving prior order,
checks readback/default unchanged, supervises all signing descendants, then restores
the exact list and verifies before deleting its own Keychain. Not Owner Mac,
self-hosted/shared runner, system domain, login/default replacement, trust-all or
partition-list workaround. Unreaped processes or cleanup ambiguity forbid upload.
Native import receives P12/password via bounded stdin, named-tools ACL only; no
private password in argv/environment. Keychain-only discovery is not proof of
real signing; actual existing-asset run remains independently reviewed/verified.
Xcode26 profile is create-exclusive under OS-resolved runner home at
Library/Developer/Xcode/UserData/Provisioning Profiles; no legacy-path fallback or
overwrite. Only owned file/directory cleanup. Manual archive/export, pinned source,
private logs/IPA within one job; prepare dependencies before signing key arrives,
retrieve separate ASC credential only after verified signing cleanup.
Main verified GitHub official signing guide and Apple DTS thread812538. The GitHub
example's trust-all/password-argv/legacy-profile-path commands are NOT adopted.

Writer lease2 completed and frozen; Main received the two new owned files and
29 focused passing tests. Revoke completed security lease3 and activate
/root/task181_review, task-198-security-20260911 lease4, role=advisor,
write=read-only, owned_paths=none, report_to=/root. Same branch/base/head above;
review frozen tools/ios_testflight_inputs.py and its test, their directly reused
certificate/profile helpers and this scope only. Verify bounded non-disclosing
errors, structural-vs-trust distinction, key separation, ES256/expiry semantics,
negative cases and no native/private/network mutation; run fictional tests only.
Main keeps the two source files frozen and handles read-only integration planning.
Review must identify exact content digests with verdict; stop on source drift,
private input need or expanded authority. Standard ACK/completion protocol applies.

Next visible Owner action, independent of source review: Google Console currently
has no project access with its signed-in account; iOS Google client availability
is UNKNOWN, not absent. Main opened account selection for Owner login to the
existing account that can access ntubtob-schedule-405614. operator=owner;
owner_gate=google_account_login; standing_authorization=IOS-TF-01;
report_to=/root; stop_only_on=login-or-MFA|unexpected-consent|target-drift.
Only login/account selection; no Request access, IAM grant, new project, OAuth
client creation or provider/callback mutation. Once signed in, Main resumes
read-only exact-client inventory. No credentials in chat or agent entry.

Security lease4 ACCEPT received/handled; independent9 tests PASS, canonical
digests match Main's source snapshot. Writer/reviewer now completed/read-only.
Main may commit/push these two source files and five Main coordination files as
one descriptive work-package checkpoint on the current release branch; no new
PR/hosted CI for this incomplete delivery. Live execution still needs complete
reviewed controller/native runner. Pause at the named Google-login stop; after
Owner login recheck exact iOS client and assign next bounded implementation.

2026-09-12 Owner Google login completed. Main read-only exact project client list
shows one Android and one Web client, no iOS client, with no filter/pagination
shown. Existing IDs not copied to repository. Google official iOS integration
requires iOS-type client plus distinct Web server audience; Flutter contract agrees.
https://developers.google.com/identity/sign-in/ios/start-integrating
Pause before new persistent Google provider resource; prior login approval is not
creation authority. PROPOSED, NOT APPROVED: create ONE iOS OAuth client named
NTUBTOB iOS Staging/TestFlight in ntubtob-schedule-405614, exact existing bundle
tw.org.ntubtob.portal, used only for IOS-TF-01 staging/Owner TestFlight. Preserve
existing Web server audience and Android client; zero update/delete of existing
clients, production callback/origin, consent/testing/tester configuration or IAM.
Do not create another project, service account, secret-bearing Web client or API
key. Creation remains stopped pending Owner exact consent and visible form
preflight; unknown required fields/expanded capabilities stop for clarification.
No claim that provider creation itself supplies runtime/signing/Apple acceptance.

Owner approved the exact ONE iOS client proposal on2026-09-12. This supersedes
PROPOSED/NOT APPROVED above only for that client; all zero-change boundaries stay.
Main rechecked the exact project's unchanged Android/Web-only list. Per
COLLABORATION8, use a visible manual Console packet, not an unreviewed credential
operator: operator=owner; owner_gate=manual_google_ios_client_creation;
standing_authorization=IOS-TF-01 plus2026-09-12 exact iOS client consent;
report_to=/root; stop_only_on=required-private-input|unexpected-capability-or-terms|
target-drift|uncertain-result. Main may populate the draft type/name/bundle only;
Owner submits Create once after visible preflight. Optional store/team/App Check
fields are not guessed or enabled. Any required additional field stops before
submission. After Owner confirmation, Main verifies one added iOS client and
exact bundle, without copying identifiers/payload to repository. Success is not
resent; ambiguous creation reconciles the client list before any further action.

Visible draft preflight complete: exact primary project; type=iOS, approved
name/bundle; optional App Store ID and Team ID empty; App Check unchecked/disabled.
Create button enabled after only the two approved text fields were filled.
No new required input or unexpected consent. Create not clicked; client-create
mutation_count=0 by Main. Owner should click the visible Create once, keep the
result page open and report completion. Do not duplicate the create action if
the result is slow/uncertain; Main first reconciles the existing-client list.

Owner reported creation complete. Main observed success dialog, one iOS addition
to unchanged Android/Web rows, then exact new-client type/name/bundle; optional
App Store/Team fields empty. Exited detail without save. Creation confirmed once,
no resend/download/clipboard; identifiers not copied into repository. This is
provider metadata readiness, not token propagation, runtime or device success.

## Real signing adapter and transport integration

New packets supersede completed writer lease2/security lease4 only for new work.
branch=codex/task-198-owner-testflight; base=5762a89c6e6451ed19f5151da1652312a9f76679;
head=c50a497aee7860b6de6f12584e0eb4d9bf7883ea; report_to=/root.
Initial dirty: Main HANDOFF, PROJECT_STATE, TASK198 task/report only.
COLLABORATION2 mandatory ACK/heartbeat/blocker/proactive completion applies;
Main remains active until both reports are handled. No private/live calls.

Writer /root/csr_writer; task-198-writer-20260911 lease3; role=codex-writer;
write=allowed; owned_paths=tools/ios_testflight_signing.py,
tools/native/ios_testflight_signing.swift, tools/tests/test_ios_testflight_signing.py.
Implement callable real-signing adapter, not another fictional-only rehearsal:
code-only preparation compiles helper and checks pinned macOS/Xcode/source;
bounded signing input via stdin only; native supervisor owns temporary Keychain,
named helper/codesign ACL, exact user search-list insertion/restoration, unchanged
default, private create-exclusive profile at Xcode26 UserData path, and fixed
manual signed archive/export with Runner-only config and Apple entitlement.
Prepare dependencies BEFORE key access; fixed workspace/scheme/configuration and
validated version/build/environment. Preserve public readiness marker; staging
only. No arbitrary command adapter, automatic provisioning or private argv/env.
Use existing bounded child supervision primitives where suitable; descendants
must stop before Keychain cleanup. Cleanup uncertainty overrides success and
forbids upload. Keep signed IPA in private same-job storage; no upload/ASC key,
new workflow, real CLI invocation, Git/cloud/provider/secret mutation in this slice.
Fictional tests cover input/path/config, failure/timeout, cleanup dominance and
fixed commands; platform-only tests must be explicit, not false native PASS.
Propose concrete interface/frame before implementing; Main handles integration.
Stop on changed targets/unsafe custody/infeasible guarantees; no scope workaround.

Advisor /root/task181_review; task-198-security-20260911 lease5; role=advisor;
write=read-only; owned_paths=none. Resolve complete protected GitHub workflow and
Windows controller transport for signing then separate ASC upload in one private
macOS job, with signing cleanup before upload subprocess receives credentials.
Check actual step-secret injection semantics versus generic no-env rule and
existing profile-only precedent; define honest minimal task exception if needed,
never silently inherit profile environment permission. Determine viable bounded
Apple upload/processing/Owner-only distribution API or tool, without public IPA
artifacts/new paid service. Source/primary docs only; no real input/Git/API mutation.
Return concrete integration contract, remaining true Owner inputs and precise
security limits. Main concurrently audits existing source/cost/dependency seams.

Transport architecture lease5 ACCEPT received/handled; Main verified GitHub
secret-read timing and Apple WWDC25 Build Upload introduction. Within IOS-TF-01,
allow ONE explicit ingress exception to generic no-env: reviewed first-party
Python step receives purpose-specific protected-environment secret(s) via that
step's env mapping, immediately removes them from its environment view, and
passes only bounded stdin to a minimal-environment child. No run-script secret
interpolation, job/global env, third-party action, GITHUB_ENV/output/summary or
raw logging. New named environment only; never profile-verification reuse.
GitHub service/runner worker may hold all environment secrets when the job starts;
not end-to-end encryption, same-UID hostile-code isolation or secure erasure.
Promise only: signing descendants never receive ASC credentials; after verified
descendant termination/Keychain/profile cleanup, a separate upload child receives
ASC input. Popping env does not prove OS memory zeroization. Reviewed runner/OS,
source/build phases and orchestration remain trusted. No private execution yet.
Sign-in Apple server key never enters signing/upload job. Private IPA stays in
same job, no public artifact/cache. Before upload, check all App internal groups
for unintended automatic distribution; do not silently disable others' settings.

Writer lease3 paused with a specific CMSDecoder implicit-decryption concern.
Main permits a bounded container-only filter before system content decoding:
outer ContentInfo must be signedData and its encapContentInfo must be id-data;
reject encrypted/nested containers, malformed lengths and trailing content.
This prevents invoking recipient-key lookup; it is NOT a CMS algorithm, signer,
attribute, trust or Apple profile-validity gate. Do not revive old custom CMS
approval or constrain real Apple digest/attribute choices. Keep raw approved
profile bytes for Xcode and label decoded data structural/untrusted. Same writer
lease3/three owned paths; add focused negative tests and deliver frozen snapshot.
Independent source review must assess this container boundary before native use.

Writer lease3 completed/frozen; Main received the three-file handoff,10 focused
PASS after container change and34PASS/2platform skips in preceding affected run.
Revoke security advisor lease5; activate /root/task181_review,
task-198-security-20260911 lease6, role=advisor, write=read-only, owned_paths=none,
report_to=/root. Branch/base/head remain the exact values above. Review all three
frozen signing files plus directly reused input/profile/config helpers; inspect
container parser/decryption avoidance, certificate/config binding, private paths,
native child/keychain cleanup and honest success classification. Run offline
fictional tests only; no native/private/Git/API mutations. Report exact canonical
digests, one consolidated verdict/findings, tests and native evidence limits.
Stop on source drift, unsafe scope or need for real input. Mandatory protocol applies.
Main concurrently prepares code-only macOS compile/rejection evidence in a separate
test path/workflow; frozen adapter stays untouched. Necessary native evidence may
use one early Draft PR per COLLABORATION9, retaining that PR for this delivery.

Main integration owns only tools/tests/test_ios_testflight_native.py and
.github/workflows/flutter-tests.yml for this next evidence addition (plus existing
coordination paths). Goal: compile the actual new Swift source and execute bounded
invalid-frame cases in existing ephemeral macOS job before any material import.
Invariant: fictional bytes only, no certificate/keychain creation, archive/upload,
private environment or new native mode; source tests do not claim signing success.
Tests: local test selection/platform skip, workflow contract, independent review,
then existing hosted macOS compile/input rejection. No additional Owner decision.

Security lease6 ACCEPT handled:10 independent PASS, frozen digests matched;
native compile/ACL/Xcode/custody remain unverified. New source acceptance does not
authorize live invocation without complete controller and independent IPA checks.
Activate same advisor /root/task181_review, claim task-198-security-20260911 lease7;
other packet fields unchanged, read-only/no owned paths/report_to=/root. Review
Main's frozen two-path native test/workflow addition and integration assumptions:
exported IPA basename versus app metadata, and temporary Keychain lock lifetime
versus bounded archive. No repeated full source review/test unless needed. Return
one verdict/limits plus exact hashes; no live or native operations. Main tracks it
and prepares a single substantive checkpoint/early Draft platform evidence run.

Lease7 ACCEPT handled for two-path compile/rejection evidence; two pre-live
integration corrections adopted within IOS-TF-01, not new Owner gates. Revoke
completed writer lease3; /root/csr_writer lease4 under same writer claim/branch/
base/head, report_to=/root, same three owned adapter paths, write=allowed.
Remove undocumented Runner.ipa filename assumption: native requires successful
export only; Python selects exactly one top-level regular .ipa under own export
root, verifies bounded same-handle owner/mode/nlink/inode/stable hash, copies it
create-exclusive to fixed private candidate.ipa and verifies identical bytes.
No metadata/ZIP/signature modification, arbitrary output path or recursive search.
Unknown/zero/multiple/nonregular/alias/changing files STOP; candidate remains
EXPORTED_UNINSPECTED and all private artifacts await controller-owned cleanup.
Before P12 import, set and read back finite2400-second idle-lock settings on the
new nonnil target Keychain only, useLockInterval/lockOnSleep true. Never pass nil,
disable locking, change default, retry unlock or extend supervisor deadline.
Idle lock is not hard destruction; process supervision/cleanup remains required.
Add focused negative/copy tests and source check; no real/native/private/Git/API
mutation. Proactively freeze/handoff; independent delta review before commit.

Writer lease4 completed/frozen;13 focused PASS, no native/private/external action.
Security /root/task181_review claim task-198-security-20260911 lease8 supersedes
completed lease7; same exact branch/base/head, advisor/read-only/owned none,
report_to=/root. Review only the three adapter correction deltas (fixed private
candidate copy and new-target finite idle settings) plus added input-suite name
in existing compile workflow. Main native test is unchanged. Verify no overwrite,
partial cleanup honesty, identity/hash binding and nonnil target/settings ordering;
run focused fictional tests, not whole prior review. Proactive complete with
hashes/verdict/limits; stop on drift/private/native need. Main repeats affected
tests and prepares exact substantive commit/push/early Draft after ACCEPT.

Security lease8 ACCEPT received/handled;13 independent focused PASS, correction
digests matched. Main41 tests39PASS/2platform skips; changed-Python quality and
diff checks PASS. Both agents completed/read-only. Main commits/pushes the ten
reviewed current paths (four new source/tests, workflow and five coordination)
and creates one early Draft PR for missing macOS compile evidence. Existing
standard public hosted CI is authorized/costUSD0; no private inputs, signing or
upload in that run. Do not merge incomplete delivery or equate compile with
native custody, full operation cleanup or TestFlight. Copy tests are fictional
byte/hash checks with mocked POSIX verifier, not demonstrated TOCTOU-race coverage.

Checkpoint pushed b0f60ac60f8e6fae99fb186931134ec23762f272. Continuing Draft PR251,
code-only run34629242446 on that exact SHA; no merge/live signing/upload. Main
tracks this run to completion while preparing remaining delivery source.

## Bounded App Store Connect upload adapter

Revoke completed writer lease4; activate /root/csr_writer,
task-198-writer-20260911 lease5, codex-writer/write=allowed/report_to=/root.
branch=codex/task-198-owner-testflight; base=5762a89c6e6451ed19f5151da1652312a9f76679;
head=b0f60ac60f8e6fae99fb186931134ec23762f272. Owned paths exactly
tools/ios_testflight_upload.py and tools/tests/test_ios_testflight_upload.py.
Initial dirty is Main task/HANDOFF coordination only. Mandatory packet protocol
applies; Main stays active monitoring hosted compile and handles completion.

Goal: callable real REST upload/reconcile adapter with no standalone live CLI,
not another success simulation. Reuse separated AscMaterial/600-second JWT and
official Build Upload API. Propose interface first; validate app bundle, exact
internal Owner group/tester and all groups' automatic/all-build access before
any reservation. Do not create/invite/modify groups or automatically distribute.
Return private typed operation IDs/receipts plus separately sanitized fixed
classification; not generic loggable dictionaries of Apple responses.

Fixed API origin/approved paths, HTTPS/no redirect, bounded response/time/request
counts, no raw URL/header/body/exception output; credential stays in memory and
never enters argv/files/signing child. Renew JWT within fixed TTL when necessary.
Source IPA fixed private candidate.ipa with approved hash/size and same-handle
owner/mode/nlink/anti-symlink/inode checks; caller must independently prove signing
cleanup, artifact inspection and exact staging scope. Adapter cannot grant those.
One operation session only; never restart successful/uncertain mutations. Create
buildUploads then buildUploadFiles once, accept only bounded non-overlapping full
file ranges and Apple-owned allowlisted storage HTTPS operations, no ASC bearer
on storage PUT, no sensitive redirect/header propagation. Official schema uses
sourceFileChecksums plural with file SHA_256; do not copy screenshot MD5 field.
Unknown destinations or response shapes stop before sending bytes; retain known
private reservation IDs for read-only reconcile, not a second reservation.
Uncertain create/PUT/commit returns uncertainty and read-only query only, even
where generic Apple guidance permits retries. No delete/retry workaround.
Processing is independently queried, bounded with pending result; COMPLETE upload
does not imply valid build, distribution, device or public readiness. Owner group
build assignment remains later controller work with a fresh exact preflight.

Tests use fictional transport/files/keys only: happy response schema, partial
upload uncertainty, unknown/redirect/unsafe URL or headers, range gaps/overlap,
oversize/private-file drift, unrelated automatic group, duplicate mutation attempt
and processing failed/pending; output sentinels absent. No private files, real
API/network calls, Git/CI/cloud/store mutation or signing source edits by writer.
Main verified public Apple OpenAPI4.4.1 and upload docs; actual key role, resource
IDs and storage route remain unverified. Stop on substantive unsafe/infeasible
contract rather than inventing capabilities. Freeze/proactive handoff for review.

Upload lease5 interface accepted: private UploadSession/Receipt, read-only
preflight/reconcile and single consumed upload operation. Allow storage hostname
only exact ASCII pattern store-[0-9]{3}.blobstore.apple.com with HTTPS443, no
userinfo/redirect, bounded signed URL from authenticated ASC response and safe
headers; this narrow Apple cluster family is not proof of actual Build Upload
routing. No arbitrary caller host override, other Apple domains or broad wildcard.
Unknown route stops without uploading bytes; known reservation is reconciled.

Code-only run34629242446 native test exited at Swift compilation; no keys/custody
reached. Its diagnostic erroneously kept first4096 bytes of deprecation warnings,
so actual compiler error was not recorded. Main independently found a Darwin
opaque-pointer initialization mismatch against Swift Foundation's Darwin path.
Main integration owns tools/native/ios_testflight_signing.swift and
tools/tests/test_ios_testflight_native.py ONLY for this bounded source correction:
initialize nullable Darwin spawn handles with paired successful-init cleanup,
and prefer bounded compiler error lines rather than truncated leading warnings.
No signing policy/command/authority changes. Upload writer retains its disjoint
two files. Tests: source/diagnostic regression, independent delta review, next
exact source CI; do not resend same failed binary or claim confirmed root cause
from missing logs. Main continues observing all jobs on the first exact run.

Main correction frozen;16 focused tests15PASS/1platform skip, quality/diff PASS.
Activate /root/task181_review, task-198-security-20260911 lease9, advisor/read-only,
owned none/report_to=/root; current branch/base/head as upload lease5. Only review
two-file Main Darwin handles/public diagnostic delta; verify initialization/defer
pairing, no native input/policy change, bounded public errors and test honesty.
No previous suite repetition, native/private/API/source mutation. Proactive
verdict/digests/limits required. Main tracks CI and upload writer concurrently.

Lease9 ACCEPT handled; first run now completed:14 jobs PASS, native compile and
dependent final gate FAIL. Main may commit/push only its two accepted source
corrections plus four Main coordination paths; keep upload writer's two untracked
paths out of that commit. Same Draft PR251, new source evidence run (not a retry
of unchanged failure). Upload writer may continue across this known Main-only
HEAD advance; Main will persist and notify exact new SHA without restarting work.

Known Main-only advance completed: HEAD/origin branch now
3484115c64080679bb58e1eedf6d3df8afc98282. This replaces upload lease5 packet HEAD
only; actor/claim/lease/base/branch/owned two files and no-live scope unchanged.
Both upload files remain untracked/uncommitted, excluded from correction. Main
continues same Draft PR251 and observes new exact-source CI without merge.

Security integration advisor /root/task181_review lease10 (same claim) supersedes
completed lease9; advisor/read-only/owned none/report_to=/root. Current packet
HEAD3484115c64080679bb58e1eedf6d3df8afc98282, same branch/base. Bounded question:
can existing artifact-only ios_candidate_inspector be safely used after keychain
cleanup without security cms implicitly consulting/mutating default keychains,
and with expected approved certificate/team/profile bound rather than internal
self-consistency only? Assess smallest code-only integration (system/structural
decode is not trust; Xcode/Apple own platform authority) and private temp cleanup
for the forthcoming controller. No new CMS algorithm/trust gate, live inputs,
native/Git/cloud/API mutations or repeated broad suite. Source/primary docs only;
return concrete minimal changes and honest verification limits. Main continues
intake/workflow integration planning while upload writer and exact CI progress.

Upload writer lease5 completed/frozen:12 new tests PASS,21 with inputs PASS,
quality/diff PASS; no real network/private/native mutation. Security lease10
inspection architecture ACCEPT received/handled. Revised native compile step in
run34630386472 on3484115c64080679bb58e1eedf6d3df8afc98282 PASS; full run pending.

Revoke security advisor lease10 for new source review. /root/task181_review,
task-198-security-20260911 lease11, advisor/read-only/owned none/report_to=/root;
same branch/base/current HEAD. Review only frozen tools/ios_testflight_upload.py
and tools/tests/test_ios_testflight_upload.py plus direct input helper; focus on
Owner-only scope, exact response/resource binding, bounded private file/transport,
credential separation, operation uncertainty/reconcile and honest evidence.
No native/private/network/Git mutation, fictional tests only; packet protocol
and proactive verdict/digests/limits apply. Main coordinates disjoint work.

Revoke writer lease5; /root/csr_writer, task-198-writer-20260911 lease6,
codex-writer/write=allowed/report_to=/root, same exact branch/base/HEAD. Owned
only tools/ios_testflight_inspection.py, tools/tests/test_ios_testflight_inspection.py,
and tools/ios_testflight_signing.py only to return bounded embedded content from
the existing container parse, without policy change. Build callable private bound
IPA inspection per architecture lease10: preserve ZIP limits/single-app, fixed
codesign integrity/entitlements and version/build, then exact approved candidate
hash/team/original profile bytes/certificate DER, not self-derived expectations.
No security cms; reuse the SAME structural signedData/id-data parse/content bytes,
never new signer/algorithm/trust gate. Exact original embedded profile mismatch
stops; do not silently update expected material or claim modern DER authority.
Fixed codesign certificate extraction in fresh private empty cwd; codesign0 leaf
must match approved P12 certificate, bounded fixed certificate output set. Decode
profile DeveloperCertificates/team must also match. Codesign integrity is not
Apple distribution/revocation/processing acceptance; authority flags stay false.

Inspection must remain within exact owned subroot of prepared signing root;
same-handle no-follow candidate snapshot/hash/identity check; private0700 dirs,
0600 files/executable0700, safe extraction, bounded output/time, minimal env/no
key/ASC stdin. All owned processes stop before bounded no-follow cleanup; cleanup
uncertainty overrides result and prohibits upload. Preserve original candidate;
other signing archive/DerivedData/export cleanup belongs to full controller.
No actual codesign/private/native/API/CLI invocation by writer. Fictional tests
cover wrong expected hash/team/cert/profile, no security call, encrypted/nested
containers, malicious ZIP/cert outputs, temp confinement and cleanup failure.
Self-review/tests then freeze/proactive handoff; independent source review before
live use. No new readiness marker or another fictional signing success gate.

Run34630386472 completed16/16 PASS on3484115c64080679bb58e1eedf6d3df8afc98282.
Lease11 REQUEST_CHANGES: upload response resource/app/parent binding incomplete;
Main owns the two frozen upload files for correction, writer lease6 remains
disjoint. Goal exact reservation/file/build ownership before bytes/VALID; core
upload adapter/tests; invariant no foreign or missing unproven association;
tests adversarial create/file/reconcile plus existing focused suite; no Owner
ambiguity. Apple OpenAPI4.4.1 lacks upload.app and file.parent linkage, so prove
membership with documented app/buildUploads and upload/buildUploadFiles related
collections, plus build included app/preReleaseVersion/buildUpload. Never invent
a required response field; missing collection proof stops. Source-only correction
and independent rereview before live use; no real Apple request yet.
Main correction now15 upload tests PASS,24 combined input/upload PASS after
three new adversarial tests first reproduced18 failing subcases. Revoke completed
security lease11; task-198-security-20260911 lease12 /root/task181_review,
advisor/read-only, owned none/report_to=/root, same branch/base/HEAD. Rereview the
frozen two-file correction only, documented related collection proof and explicit
contradiction handling; no live API/native/private/Git mutation. No full prior
suite repetition. Proactive verdict/digests/tests/limits; Main proceeds integration.
Security lease12 ACCEPT handled; upload correction frozen. Writer lease6 frozen,
23 tests PASS. Revoke security12 for lease13 (same actor/claim/role/base/HEAD),
read-only independent review of writer6 inspection three files only; fictional
focused tests, no private/native/API/Git mutation. Mandatory protocol unchanged.
Revoke writer6 for lease7 (same actor/claim/branch/base/HEAD/report_to), owned only
tools/ios_testflight_intake.py and tools/tests/test_ios_testflight_intake.py.
Build callable Windows private material intake reusing reviewed handle/ACL custody,
fixed existing signing root and explicit private paths for two distinct downloaded
p8 keys. No network/Git/native signing, copies, saved payloads, or repair/ACL edits.
One hidden input collection with length-only ASCII output, bounded P12/password/
certificate/profile and two distinct key validation in memory. Keep Apple Login
material separate from signing/ASC transfer, no payload repr/log/argv. Existing
exact identifiers/config supplied as typed arguments, not re-requested or derived
from artifact; immutable raw profile structural decode only. Main owns callable
runner/controller and workflow integration; intake has no dispatch or standalone
mutation authority. Tests fake Native/readers/prompts only, then freeze/review.
Writer7 may implement owned-file Native metadata subclass retaining every existing
handle/path/type/link/reparse invariant, fixed limits262144 profile/65536 cert-P12/
4096 p8; original globalLIMIT/Native/ACL policy unchanged. No Downloads ACL repair.
Security13 REQUEST_CHANGES handled: Main owns frozen inspection two files for
bounded correction restoring existing metadata/distribution validators and checking
process-group disappearance before cleanup. Writer7 intake stays disjoint. Main
also owns tools/ios_testflight_runner.py and its focused test for end-to-end private
phase orchestration; original expected material and no-live evidence remain binding.
Main inspection correction25 focused PASS (12 inspection/13 signing), includes
full synthetic ZIP positive/negative path (POSIX metadata/cleanup and codesign
mocked explicitly), restored old validators and ESRCH-only group stop proof.
Existing test __new__ mock polluted later Tree construction; changed to module
class mock, not product workaround. Revoke security13; lease14 same actor/claim/
role/branch/base/HEAD, readonly correction rereview of inspection/test and unchanged
four-line parser return only. No native/private/realAPI/Git/edit; packet protocol
unchanged; reviewer completion triggers Main intake review, not automatic live run.
Security14 ACCEPT handled. Writer7 intake frozen9 PASS; security15 same claim/
actor/readonly/branch/base/HEAD reviews only intake two files and direct custody/
validation helpers, focused fake tests/no live private/native/API/Git/edit.
Writer8 supersedes completed7, same actor/claim/branch/base/HEAD/report_to;
owned tools/ios_testflight_runner.py and tools/tests/test_ios_testflight_runner.py
(Main releases these two integration paths). Callable phase orchestration only:
sign then exact-bound inspect, confirmed process/custody cleanup before upload,
owned-root cleanup excluding candidate before ASC phase and final cleanup afterward.
Prepared root identity and OS private temp boundary required, no-follow deletion,
never cleanup while process/custody unresolved. Upload once plus read-only reconcile,
no group/distribution or new transfer authority yet. Tests fake all phases/transport.
Main owns tools/ios_testflight_wire.py, its test and forthcoming exact workflow/
operator integration. Wire uses fixed purpose-separated finite chunks with overall
private step environment <=144KiB (signing frame<=128KiB, ASC<=8KiB), to remain
below Darwin exec environment budget; larger input rejects locally before dispatch.
No secret inspection to choose a larger limit; no raw key in argv/log/artifact.
Security15 intake ACCEPT handled. Main wire5 tests PASS/quality PASS; freeze
tools/ios_testflight_wire.py and its test for security16 (same actor/claim/readonly/
owned none/base/branch/HEAD/report_to). Review finite secret set, main/workflow/run1
binding, TTL/hash/chunk/index/size and consume-all-on-error, purpose separation and
honest inherited-environment limitation; fake tests only/no private/native/API/Git.
No operator/workflow deployed yet. Main continues their implementation while
writer8 completes phase runner; mandatory ACK/heartbeat/proactive completion apply.
Security16 wire ACCEPT handled; writer8 runner frozen8PASS/1POSIXskip. Security17
(same claim/actor/readonly/base/branch/HEAD/report_to) independently reviews runner
two files plus called accepted adapters, mocks only/no native/private/API/Git/edit.
Writer9 changes same actor to advisor/read-only/owned none (revoke writer8); bounded
preparation audit: current iOS project is SwiftPM, but signing.prepare incorrectly
requires CocoaPods files. Identify exact supported code-only dependency preparation
and package-resolution path used by native fresh DerivedData, plus other guaranteed
pre-sign failures; no private/native/network/Git/file mutation, local source only.
Main fixes confirmed integration contradictions; no Owner gate for ordinary source
correction and no private input until complete reviewed operator is ready.
Security17 runner ACCEPT and advisor9 preparation audit handled. Public completed
CI job103365523222 confirms actual SwiftPM fetches GoogleSignIn/LINE and generated
Package.resolved paths, no Pods installation. Writer10 supersedes advisor9,
codex-writer same actor/claim/base/branch/HEAD/report_to; owned only existing
tools/ios_testflight_signing.py, tools/native/ios_testflight_signing.swift and
tools/tests/test_ios_testflight_signing.py. Fix SPM preparation/coherent cache:
require generated local SPM manifest, conditional Pods locks only when Podfile
exists; pre-key resolve into owned root SourcePackages/DerivedData, same fixed
archive clone path. Preserve signature/plugin validation and manual signing;
bind generated resolved files and dependency receipt before keys. Only exact two
generated Package.resolved untracked paths may be allowed, with digest checked
again before native; tracked/unrelated dirty paths remain forbidden. Fake tests
only/no actual resolve/build/private/API/Git mutation, freeze and independent review.
Main code-only workflow preparation uses pinned flutter build ios --release
--no-codesign --config-only --no-pub after pub get/precache, not dummy Pods.
Main integration owns tools/ios_testflight_hosted.py, its tests and
.github/workflows/ios-owner-testflight.yml. First-party only private ingress,
separate minimal-environment sign/upload stdin workers, exact prepared receipt,
single exclusive consumed marker/run1, bounded IPC/output/children and fixed safe
public result. No artifact/cache exports. Signing STOP with confirmed-stopped
workers still requires owned-root cleanup; unknown worker/custody never blind-delete.
Workflow remains manual/protected/main-only, not dispatched by source tests.
Writer10 frozen17PASS; security18 supersedes completed17, same claim/actor/readonly/
base/branch/HEAD/report_to, ownednone. Review only signing Python/Swift/test SPM
correction and direct cleanuphelper interactions, no native/private/API/Git/edit.
Actual source prepared receipts require nonempty dependency_digest; Main hosted
serialization must retain it. Newresolve process proves ESRCH before cleanup;
unknown compiler/resolve states retainroot. Minimaltargeted tests/packet protocol.
Security18 ACCEPT handled. Writer11 supersedes10, same actor/claim/codex-writer/
base/branch/HEAD/report_to; owned tools/ios_testflight_dispatch.py and its test.
Callable one-session GitHub dispatch/finite private-secret transport only, fixed
new ios-owner-testflight environment/workflow (never profile-verification).
Read-only exactOwner/main/source/workflow/reviewer/main-only protection preflight;
refuse any existing transfer secret, pack-size check before dispatch. One dispatch,
run-id/attempt1/nonce binding, wait for exact protected pending deployment, encrypt
and PUT six fixed purpose-separated names once, then one exact environment approval
under IOS-TF-01 standing approval (not remove/bypass protection). Partial/unknown
PUT stops approval and records attempted names for bounded deletion/absence checks;
no blind retry. Return compact progress, bounded same-run observe and once-only
cancel/cleanup methods, no owner prompts/secret reads/CLI/environment creation here.
Source tests fake GitHub only. Main later composes reviewed caller; no live calls.
Writer11 completed/frozen10tests PASS; fixed protected job id/name owner_testflight.
Security19 supersedes completed18, /root/task181_review same claim/base/branch/HEAD,
advisor/read-only/ownednone/report_to=/root. Review only dispatch module/test and
wire/primitives direct boundaries: exact run/job/pending policy, no resend,
partial/uncertain PUT/approval/cancel and absence vs HTTP uncertainty. Frozen LF
digests c5502f0966eafdbef029dc7d3e089fecb892286bac6b49431ac03f5ed6765613 and
2df23c4cfc12651c96554efc7cf12e55d02831825e891a9afec183fe201b3362.
No private/native/API/Git/CI/edit; fictional tests only, mandatory ACK/completion.
Main concurrently finishes separate hosted controller/workflow, not accepted yet.
Writer12 supersedes completed11, same actor/claim/role/base/branch/HEAD/report_to.
Owned tools/ios_testflight_environment.py and its test. One-shot new dedicated
ios-owner-testflight environment bootstrap, no private input/CLI/live API: first
verify authenticated Owner/repo and absence; create exact Owner required reviewer,
prevent_self_review=false, can_admins_bypass=false, custom main-only policy, then
one branch rule and readback. Never modify/delete/reuse an existing environment,
overwrite secrets, remove protection or auto-retry uncertain/partial operations.
Read-only inspect existing correct policy allowed. Verify public official API
contract; fake tests first. No native/private/Git/CI mutation. Standard packet applies.
Security19 REQUEST_CHANGES handled: Main owns narrow dispatch public-evidence
correction separating current absence from unresolved retention after HTTP ambiguity.
Writer12 stopped without edits: official REST write contract omits admin bypass;
actual read-only existing profile environment returns can_admins_bypass=false.
Use exact Owner UI setup of NEW environment followed by strict readback; no
undocumented write, no weak environment bootstrap. That manual setup is a named
Owner gate, not another per-SHA signing approval. Existing environment untouched.
Main integration additionally owns .github/workflows/python-tests.yml to run the
new testflight focused tests in the existing selected tooling job; no extra job,
new PR, or private input. Hosted workflow source only until full local operator.
Security20 supersedes completed19, same claim/actor/read-only/ownednone/base/branch/
HEAD/report_to. Frozen Main hosted controller/test and ios-owner-testflight workflow,
existing python-tests focused suite addition, plus dispatch retention correction.
Main102 tests99PASS3POSIXskips, quality16Python PASS/diffcheckPASS; no real custody.
Review known-stop vs uncertainty cleanup, same-handle state/run1/TTL, sign/ASC child
separation, pinned no-cache/private-artifact workflow and safe public evidence.
No private/native/realAPI/Git/CI/edit; Main coordinates report while files frozen.
Digests supplied in mandatory assignment packet; ACK/heartbeat/completion required.
Security20 REQUEST_CHANGES handled: a pending upload's only private receipt must
not disappear during automatic cleanup. Main has NOT invented a public-log or IPA
artifact transport. Workflow is explicitly disabled (false job guard), hosted live
entry also rejects before context/material; cleanup refuses any known remote receipt.
This checkpoint is dormant source, not a complete runnable controller. Before
activation implement durable private receipt handoff/ack and local journal, then
independent integration review. Main14hosted tests13PASS1skip include four remote
states refusing receipt deletion. Security21 same reviewer/readonly/ownednone/HEAD
reviews only these three-path changes for dormant-checkpoint acceptance, not live
acceptance. Standard packet protocol; no real/private/native/API/Git/CI/edit.
Security21 ACCEPT handled for dormant checkpoint only, independent25tests24PASS1skip.
Both reused agents completed/read-only. Main104TestFlight tests101PASS3skips plus
18workflow-contract tests17PASS1skip; working-tree quality16Python and diffPASS.
Commit/push reviewed source plus Main coordination to current shared branch/same
DraftPR251; normal selected code-only CI may run, never dispatch private workflow.
No merge/activation; next Owner action is exact new protected environment setup.
This is a manual configuration stop, not completion of IOS-TF-01. Resume remaining
local operator/private receipt handoff, then batch inputs/staging/Owner distribution.
Checkpoint171efa870767f2aac161497a402d23869d24176a pushed; same DraftPR251.
Normal CI34636351770 Windows tooling PASS, Ubuntu new suite fails two tests plus
one assertion: fictional Windows C:/ paths interpreted by POSIX Path are relative.
Main owns test_ios_testflight_intake.py correction only: explicit PureWindowsPath
test seam for fake Windows custody, preserving real parser/ACL/no-read guards.
No product change or skip. Security22 same reviewer/readonly/ownednone/report_to,
base unchanged/currentHEAD171efa870767f2aac161497a402d23869d24176a; review focused
fixture correction and tests, no native/private/API/Git/CI/edit. Packet applies.
Security22 ACCEPT handled, independent10testsPASS and exact LFdigest matched.
Main105tests102PASS3skips, quality/diffPASS. Push test-only correction with Main
state/report/review to samebranch/PR; next normal CI supersedes prior failed run.
No private dispatch, merge or activation; both agents completed/read-only.

## Resume after protected environment verification

Owner completed new environment setup. Main verified exact sole Owner reviewer,
prevent_self_review=false, can_admins_bypass=false, custom main branch only and
zero environment secrets. No API mutation or private payload read. This gate is closed.
Checkpoint: complete interrupted-operation recovery and the real local operator;
core hosted/upload/dispatch plus local journal; no repeated successful/uncertain
mutation, no private identifiers in logs, no Owner secret input persistence;
focused restart/ambiguity/cleanup tests and independent integration review;
remaining actual input/runtime/device gates are not source-completion claims.

All new packets: branch=codex/task-198-owner-testflight;
base=5762a89c6e6451ed19f5151da1652312a9f76679;
head=2007016fa0bdd18bcfd2c546800e52a7ca477bbc; report_to=/root.
Revoke completed security22; security23, task-198-security-20260911,
actor=/root/task181_review, role=advisor, write=read-only, owned_paths=none.
Bounded architecture review: smallest durable non-replay recovery. Evaluate exact
App/version/build read-only rediscovery with public artifact fingerprint and private
IDs only in memory versus encrypted private receipt transport. No speculative new
credential/artifact service, no Owner input persistence or fake remote acknowledgment.
Identify necessary retained fields and fail-closed ambiguity cases before implementation.
No private/native/API/Git/CI/file mutation; report contradiction immediately.
Revoke completed writer12; advisor13, task-198-writer-20260911,
actor=/root/csr_writer, role=advisor, write=read-only, owned_paths=none.
Audit minimum Windows durable single-operation journal and local caller integration
using existing custody/dispatch primitives. Identify exact preflight/input ordering,
restart state, missing recovery hooks and complete operator sequence; no edits,
private/native/API/Git/CI mutation. Mandatory ACK/heartbeat/completion applies.

Advisor13 completion handled. Revoke advisor13; activate writer14, same actor,
claim/base/head/branch/report_to, role=codex-writer, write=allowed. Owned only
tools/ios_testflight_journal.py and tools/tests/test_ios_testflight_journal.py.
Implement one bounded append-only sanitized JSONL journal at fixed KnownFolder
private directory, exclusive same-handle Windows share0 lock, ancestor locks,
owner-only ACL/no reparse/link/identity checks, flush and same-handle readback
before returning an event acknowledgment. No Owner input, raw receipt/ASC IDs,
private path or secret persisted. Existing corrupt/incomplete journal only supplies
read-only prefix; cannot append or authorize any mutation. No automatic reset,
delete/archive/second operation. First implementation supports one delivery only.
Main owns dispatch hooks/recovery, hosted integration and operator. Source tests
fake Native; writer supplies strict event schema and Journal.record/events/close
contract, no live input/file custody/API/Git/CI. Single journal is the task's one
durable sanitized operation record, not a private-input transcript.

Security23 architecture ACCEPT handled: replace private receipt export/ack with
strict GET-only ASC rediscovery and a non-secret exact-run artifact fingerprint.
No new encryption key, artifact export or private ID log. Persist local intent
before dispatch; hosted fingerprint contains run/SHA/nonce/version/build/hash/size
after inspection and before upload. A remote print/flush is NOT local durable ack.
Local operator reads only exact bound job logs, validates one fingerprint and
records it before recovery use. Missing/lost fingerprint or missing checksum is
STOP, never fresh upload; this trades recovery availability for no new secret store.
ASC exact App/version/build must have one upload and one related IPA file with
matching SHA_256/size/type plus exact completed build/app/version linkage; IDs
stay memory-only. Metadata matching is not a claim Apple independently rehashed.
Existing unknown cleanup remains STOP; confirmed owned-root cleanup may remove
ephemeral state with no private IDs because recovery now depends on public binding.
No recovered VALID result means distribution happened; distribution is separate.
Main owns tools/ios_testflight_recovery.py, its test, dispatch/hooks, hosted/log
projection and forthcoming local operator plus tests/workflow. Workflow keeps its
disabled guard until consolidated source acceptance. No real/private operation yet.

Writer14 completion handled; journal two files frozen8testsPASS. Main dispatch
before/after durable hooks, nonce-bound run discovery and exact completed-job log
fingerprint ingestion plus GET-only ASC rediscovery frozen; combined28testsPASS.
Security24 supersedes23, same claim/actor/branch/base/head/report_to, advisor,
read-only/ownednone: review journal/dispatch/recovery and their exact three tests.
Verify crash-before/after side effect, torn-prefix no mutation, no second operation,
same-handle Windows persistence, pure-GET ASC checksum/linkage and privacy. Fake
tests only/no private/Native/API/Git/CI/edit. Main concurrently integrates separate
hosted and local operator files; these six reviewed paths stay frozen.

Security24 ACCEPT handled, independent28testsPASS; no live acceptance. Revoke
writer14 (completed/read-only), activate writer15 same actor/claim/base/head/branch/
report_to, codex-writer/writeallowed, owned only tools/ios_testflight_owner.py and
tools/tests/test_ios_testflight_owner.py. Implement bounded ASC read-only inventory
and separate single Owner-group build assignment adapter. Inventory exact bundle
App, supplied Owner email, unique existing internal group/tester and all groups
auto-distribution disabled; no creating users/testers/groups/invitations. Missing
group/tester returns fixed preparation-required state. One assignment only after
exact recovered VALID build and fresh Owner-only/no-other-target evidence, caller
durable before/after hooks and staging acceptance; existing assignment is read-only
already-applied. Uncertainty only GET reconcile/no POST repeat; no external review/
public release/metadata correction. Verify current official endpoint/schema and
fake success/foreign-scope/uncertainty tests. No real API/private/Git/CI actions.

Writer15 completion handled: Owner inventory/assignment adapter14fake testsPASS,
source only. Main complete sign/upload CLI now combines strict metadata preflight,
existing hidden P12/ASC-only custody (does not request/read unused Apple Login p8),
ASC target/build inventory, journal intent, protected dispatch and one-shot secret
transport, exact terminal job result/fingerprint, cleanup and GET-only ASC match.
Staging URL/LINE/Web audience come from exact isolated service metadata in memory;
metadata presence is NOT Apple configuration/schema/functional acceptance. No
distribution CLI or fabricated StagingReadiness; actual staging postchecks remain
required before later Owner-group assignment. --recover never signs/uploads; it
may only exact-run cancel/attempted-secret cleanup, then fresh ASC-only input/GET.
Original input TTL remains2h; dispatch request budget512 accommodates minute
observations without premature exhaustion. Damaged journal prohibits all mutations.
Source activation proposed in this same delivery; no actual dispatch until commit,
independent acceptance, normal CI and main integration. Cost stays standard public
GitHub macos-15 with no artifact/cache export or paid service.
Main146tests142PASS4platformskips,18workflow tests17PASS1skip,14PythonqualityPASS.
Security25 supersedes24; same claim/actor/base/head/branch/report_to, advisor,
read-only/ownednone. Consolidated review entire uncommitted TestFlight implementation
and test delta, owner adapter and workflow activation. Verify live caller can only
select isolated staging/Owner App, no private input logs, clean binding/run/TTL,
durable non-replay/GET recovery, minimal key purpose, secret/worker cleanup and
honest pending-vs-failure evidence. All source paths frozen; Main only coordination.
No private/Native/liveAPI/Git/CI/edit; focused fake tests and direct code only.

Security25 REQUEST_CHANGES handled; no activation/commit/dispatch accepted yet.
Main owns normal failure cancellation correction, fresh bounded cleanup observation
and its tests. Revoke completed writer15; writer16 same actor/claim/base/head/branch/
report_to, codex-writer/writeallowed, owned only tools/ios_testflight_staging.py and
tools/tests/test_ios_testflight_staging.py. Implement metadata-only staging ownership
comparison using the already accepted TASK-157 immutable revision and image digest
in the archived Gate B receipt, not a new caller boolean. Verify current service
template and every reachable traffic revision keep the exact accepted staging
runtime identity and immutable, staging-project Secret versions, including the DB
reference; reject unversioned/mixed/unknown bindings, sidecars/volumes or ambiguous
traffic. Fetch metadata only with injected bounded JSON CLI; never Secret payload,
DB connection, private receipt or old helper execution. If historical receipt cannot
prove a binding, return fixed STAGING_OWNERSHIP_UNVERIFIED before private input.
Source-only tests include valid equivalence and drift/adversarial cases. Investigate
official Cloud Run immutability semantics if needed; report unsupported inference
immediately. Main retains operator integration. No real API/private/Native/Git/CI.
Mandatory received/executing ACK, 10-15 minute heartbeat, blocker and proactive
completion with SHA/dirty paths/tests/findings/limits/external mutations applies.

Writer16 completion handled; two owned paths frozen13fake testsPASS, no external
mutation. Main integration uses the exact final service snapshot validated by the
ownership comparator, never a separate unverified metadata read. Baseline server
creation timestamp pinned to Main read-only observation2026-08-26T05:35:31.015912Z;
version createTime must predate it to reject recreated Secret names. This proves
retained accepted bindings only, not current DB contents/IAM/schema/Apple readiness.
Current image may differ from baseline if immutable staging-project digest pinned;
new runtime/deploy still requires independent target and functional postchecks.
Main normal failure correction permanently switches session to cleanup-only,
renews bounded GET/cancel/owned-DELETE budget once without extending input TTL,
cancels known unfinished run at most once, cleans even after cancel error and
observes actual terminal state. Torn journal cannot mutate; unknown cancel not resent.
Main42 focused operator/dispatch/staging testsPASS. All source now frozen.
Security26 supersedes completed25; same claim/actor/base/head/branch/report_to,
advisor/read-only/ownednone. Review two corrections and operator integration:
tools/ios_testflight_{operator,dispatch,staging}.py plus their three tests, in context
of previously reviewed activation/journal/owner/recovery. Accept only if both prior
findings resolved without weakening D4 or non-replay. Fake tests/source/primary docs
only; no private/Native/liveAPI/Git/CI/edit. Mandatory packet ACK/heartbeat/completion.

Security26 ACCEPT received/handled42independentPASS; six frozen LF source hashes
matched. Both security25 findings resolved for retained-binding/source scope only.
Main166TestFlight tests162PASS4platformskips; workflow18tests17PASS1skip; quality16
Python/diffPASS. Both agents completed/read-only; Main resumes integration.
After this reviewed source is committed, normal selected CI passes and PR251 is
merged, the task-listed Windows entry is py -3.10 -m tools.ios_testflight_operator
with --preflight, --execute or --recover. Preflight is read-only and precedes all
private prompts. Execute authorizes one real signing/upload under IOS-TF-01 only,
not Owner-group distribution; recover never signs or uploads. No old external
helper, new key creation, provider mutation, Secret payload inspection or DB access.
Actual staging Apple/schema/deploy and Owner-only assignment/device remain separate
required transitions within this package, not implied by a source or upload PASS.

Reviewed source pushed8a37459d2bcca32bb002605b0816a3d3c1c693dc; normalCI34644785015
started, no private workflow. Actual read-only metadata preflight found a Windows
executable-resolution defect: bare gcloud cannot spawn, resolved gcloud.CMD exits0
with bounded project metadata. No target/Secret payload read or external mutation.
Main owns operator+test correction only, reuse existing repository shutil.which
pattern and add actual fictional Windows batch regression; no shell=True, changed
environment/secret access or authority expansion. Rerun exact metadata verifier
after independent delta review; unverified preflight is not ownership drift proof.

Security27 supersedes completed26, same actor/claim/base/branch/report_to; current
HEAD8a37459d2bcca32bb002605b0816a3d3c1c693dc. Advisor/read-only/ownednone. Review
only Windows CLI resolution correction in operator and its test; two files frozen,
14 focusedPASS including real fictional .cmd spawn. No shell or live mutation
introduced; primary adapter remains bounded stdout/stderr-discard/no-retry.
ACK/heartbeat/proactive completion packet applies. No private/native/liveAPI/Git/CI/edit.

Security27 ACCEPT handled14independentPASS. Resolved actual CLI now reaches live
metadata; comparison shows exact account/environment/Secret refs/spec/network
retained, but single-container autogenerated name differs with the accepted newer
image. Env order differs only in raw list; normalized env comparison already passes.
Main owns staging verifier+test narrow correction: exclude container display name
from retained-binding equality, still exactly one container/no volumes/sidecars,
validate name shape and retain every other non-image container field. No runtime
mutation or relaxation of Secret/account/data proof. Source-only negative tests
must retain command/env drift rejection. This is a new evidence-backed false
positive correction, not overriding an unknown ownership result.

Security28 supersedes27, same actor/claim/base/head8a37459d2bcca32bb002605b0816a3d3c1c693dc/
branch/report_to; advisor/read-only/ownednone. Two staging files frozen; review
single-container name normalization and new positive/command-drift/invalid-name
regression only. Prior Windows correction frozen accepted27. Main28combinedPASS.
No private/Native/liveAPI/Git/CI/edit; mandatory ACK/heartbeat/proactive completion.

Security28 ACCEPT handled28independentPASS. Real metadata-only comparator now
STAGING_OWNERSHIP_RETAINED; no Secret payload/DB access, all runtime/schema/release
flags false. Main169tests165PASS4platformskips,quality4Python/diffPASS. Commit/push
both accepted local compatibility corrections to samePR251; final normalCI required.
App Store Connect browser read-only check confirms exact NTUBTOB App, no builds
and no internal groups. Next Owner UI preparation is exactly one internal group
NTUBTOB Owner Internal, automatic distribution disabled, only existing Owner user;
no external tester, public link, other invitation or new account. Then reviewed
local private intake may proceed; never put password/p8/P12 content in chat.

Execution-tool gate: exact nine-file commit/push was rejected twice before command
execution, even after read-only origin fetch/push URL verification and citing Owner
standing authorization. No Git/index mutation occurred; do not bypass or split the
rejected action. Ask current explicit confirmation for this correction commit/push
to https://github.com/r06521541/NTUBTOB-management-system.git, branch
codex/task-198-owner-testflight, samePR251. This is tool auto-review, not a new
repository per-SHA policy. Current pushed8a37459d2bcca32bb002605b0816a3d3c1c693dc
has CI34644785015 SUCCESS16/16; it does not cover the nine remaining dirty paths.
No ongoing agents/watchers; source169tests165PASS4skips and actual metadata proof
accepted. Resume exact correction push, finalCI/main integration, then private/UI gates.

Owner2026-09-12 explicitly confirmed the pending exact nine-file commit/push to
the named existing repository and PR251. Main verified branch/HEAD/remote/dirty
scope unchanged and reran169tests165PASS4skips,quality4PythonPASS. Resume commit/
push, normal finalCI and existing authorized merge; private/UI gates unchanged.

## Confirmed pre-execution input repair

PR251 merged48232c548d486c8175ac990dd91d2f68d218544b after CI34688813903 SUCCESS16/16;
clean merged-main preflight returned PREFLIGHT_PASSED. Owner created the exact
internal group with only their existing user; UI readback1tester/0builds/manual
distribution. Owner then reported INPUT_REJECTED after all seven hidden fields.
Main read-only check: signing-workflow runs0, dedicated environment secrets0,
operation journal absent. No private values/payloads read; only prompt/length
progress was retained during diagnosis. Owner answered that path quotes were not
removed; fictional reproduction confirms quoted paths fail in the released parser.
This establishes a format defect, not validity of the other private inputs.

Main remains task-198-main-20260911 lease1, sole writer for this bounded repair,
report_to=/root. Branch codex/task-198-private-input-recovery, base/head
48232c548d486c8175ac990dd91d2f68d218544b. Owned: tools/ios_testflight_intake.py,
tools/ios_testflight_operator.py, their two direct tests, and this task's existing
HANDOFF/PROJECT_STATE/report/review. Prior writer and security28 are completed.
Accept exactly one balanced double-quote wrapper on a private path, with all
absolute-path/type/size/ACL/handle guards unchanged. Syntactic input rejection may
re-prompt only that field, at most3attempts, in the current process before any
operation intent; already-valid fields stay memory-only. No cryptographic/file/
network/dispatch retry, persisted inputs, deadline extension or new authority.
Return fixed field/stage reasons without values, paths, exception text or hashes.
Test syntax, cancellation, exhaustion, no-repeat fields, custody failures and
zero execution on input failure; independent security review then normalCI/merge.
This is a substantive repair after mergedPR251, not a status-only PR. Old process
inputs are unavailable; a fresh reviewed/preflighted entry still needs Owner input.

Owner subsequently explicitly requested safe reuse through an editable local JSON.
This repair also owns tools/ios_testflight_settings.py and its direct test. Narrow
exception to memory-only metadata: six exact fields (Team, ASC key/issuer, iOS
client, Owner email and ASC path) may persist in one Owner-editable JSON under the
existing private KnownFolder custody directory, outside Git/cloud-sync paths.
Never persist passwords, PEM/key bytes, tokens, approval, target overrides or a
session. Fresh preflight and original operation/journal rules still apply. Create
only an empty template, never overwrite; strict bounded same-handle/ACL read,
duplicate/unknown fields rejected, field-only validation before password/key reads.
Owner edits individual fields; agent never reads their populated JSON directly.
Passwords remain hidden/in-process only. No encrypted secret cache in this scope.

Security29 assignment: task=TASK-198; branch=codex/task-198-private-input-recovery;
base=head=48232c548d486c8175ac990dd91d2f68d218544b (six frozen dirty Python files).
actor_id=/root/task181_review; role=advisor; claim_id=task-198-security-20260911;
lease_version=29; write=read-only; owned_paths=none; report_to=/root.
Scope: independent review of intake/operator/settings and their three direct tests;
safe metadata persistence, quote parsing/bounded correction, native creation/read
ACL/handle/size/non-overwrite guards, no secret cache, no mutation/authority retry.
Stop: unexpected source change, private payload need, external mutation, scope drift.
Immediate received/executing ACK with report_to=/root; heartbeat10-15min; blockers
immediate; final proactively report verdict/full HEAD/dirty paths/tests/findings/
limits/external mutations. Main remains active until completion is received/handled.

Reviewed-interface plan (use only after this repair is accepted/merged):
`py -3.10 -m tools.ios_testflight_operator --prepare-inputs` creates the empty
template at KnownFolder LocalAppData/NTUBTOB-AppleDistribution-CSR/testflight-inputs.json.
Do not recreate if it exists. Owner edits only six string values in that file,
never password/key payload; use forward slashes in asc_p8_path to avoid JSON
backslash escaping. Keep commas/quotes and save UTF8 (BOM accepted).
`--check-inputs` checks fresh preflight + metadata syntax only, no password/key read
or dispatch; all bad field names reported together. `--execute --settings` reads
the same file with fresh preflight, then asks only the hidden P12 password.
Do not send filled JSON to chat or store it in Git/cloud-synced folders. Syntax
errors: edit indicated field; key/custody/runtime failure: inspect fixed reason,
never blindly repeat an uncertain execution. `--recover` remains cleanup/GET-only.

## Approved ASC-only private custody import

PR252 merged b428ab9d25702c0c7516db11e0c20030f09591d6; CI34693162874
SUCCESS16/16, clean-main preflight and empty-template creation succeeded. Owner
filled metadata; SETTINGS_READY passed, but execute returned ACL_REJECTED. Read-only
checks found zero signing runs/secrets and no journal. Fixed settings/signing root,
P12/certificate/profile ACLs pass. Owner identified their local Apple folder;
metadata-only checks found6files (2p8), no subdirectories/reparse points; folder
and both p8 have4 inherited ACEs, current Owner matches. This is an ACL contract
mismatch, not evidence of exfiltration. Do not pick a key by filename length.

Owner explicitly approved on2026-09-12: copy ONLY the ASC p8 selected by the JSON
into the existing protected private folder and update only asc_p8_path; preserve
all original files, other five values and the separate Apple Login key. One extra
protected local key copy is authorized. This narrow import supersedes earlier
no-copy rule ONLY for that file; no source folder/file ACL repair or broad copying.
Source regular single-link current-Owner local non-reparse file, bounded4096,
locked same-handle snapshot; source inherited ACL is accepted ONLY at this import
boundary. Never weaken normal custody. Destination fixed asc-upload.p8, CREATE_NEW
with explicit Owner ACL, flush/readback; no overwriting or deleting source/target.
Settings retain Owner-only ACL and other fields. Native fictional probe rejected
locked atomic replacement with ERROR_SHARING_VIOLATION, including outside sandbox.
Do not relax sharing/close the lock or claim atomic replacement. Instead retain a
fixed metadata-only testflight-inputs.pre-import.json backup, CREATE_NEW with the
same private ACL and flush/readback, before key copy or settings mutation. Hold the
original settings write-capable handle denying other write/delete throughout;
update only the path using that handle after the backup/key are verified. An
interrupted in-place update may leave the main JSON incomplete, but the six fields
remain in the protected backup. Partial state stops unresolved, never automatic
retry/overwrite/restore/deletion. This backup is not another key/password cache.
Read-only import preflight is separate from one-shot import, and completed import
is never recopied. No network/key use/sign/upload in the callable importer. Normal
operator clean-main/GitHub/staging preflight precedes both CLI modes. Key filename
must bind ASC Key ID where the provider's standard filename is present; do not
infer API validity from filename/PEM. Actual ASC scope validation remains later.

Main task-198-main-20260911 lease1, /root, owns intake/operator, their direct tests,
and existing task/HANDOFF/PROJECT_STATE/report/review. Branch
codex/task-198-asc-private-custody; base=head=b428ab9d25702c0c7516db11e0c20030f09591d6.
Main adds metadata-only asset checks before hidden password and to --check-inputs.

Writer assignment: task=TASK-198; branch=codex/task-198-asc-private-custody;
base=head=b428ab9d25702c0c7516db11e0c20030f09591d6; actor_id=/root/csr_writer;
role=codex-writer; claim_id=task-198-writer-20260911; lease_version=17;
owned_paths=tools/ios_testflight_key_custody.py,tools/tests/test_ios_testflight_key_custody.py;
write=allowed; report_to=/root. Implement bounded callable check_import(google_web=)
and import_key(google_web=), returning only fixed classification strings; export
REASONS and Rejected. No own CLI, source edits elsewhere, Git/cloud/real-private
operations. Design source locks and backup-based JSON preservation first; report any
necessary API change before broadening. Fake fixtures only incl native disposable
Windows copy/edit/failure tests. No generic vault/new operation journal framework.
Stop: source ambiguity, overwrite need, private asset/external call need, ownership
conflict. ACK received/executing immediately with report_to=/root, heartbeat10-15min,
blocker immediate; proactively send full HEAD/exact dirty paths/tests/findings/limits/
mutations on completion. Main stays active and handles completion before proceeding.

After acceptance/normalCI/merge only: --check-key-import performs metadata-only
preview and must return ASC_IMPORT_READY before the approved one-shot
--import-asc-key. ASC_IMPORT_PRESENT means existing metadata only, not verified key
content; preview never reads p8. Completed import_key may compare only original
selected source/copy read-only and never recopy. After ASC_IMPORT_COMPLETE use
--check-inputs for all required file custody before requesting hidden password.
No actual import has run during implementation. Backup retains metadata, not P12
password; unclear/partial states stop with original keys and any backup preserved.

Security30 assignment: task=TASK-198; branch=codex/task-198-asc-private-custody;
base=head=b428ab9d25702c0c7516db11e0c20030f09591d6. actor_id=/root/task181_review;
role=advisor; claim_id=task-198-security-20260911; lease_version=30;
write=read-only; owned_paths=none; report_to=/root. Six frozen source/test files:
tools/ios_testflight_{intake,operator,key_custody}.py and their three direct tests.
Review ASC-only import, original/backup/saved-field preservation, inherited-ACL
exception, locked handles/no-overwrite/partial STOP, metadata-only pre-password
checks/preview, fixed diagnostics and unchanged sign/upload authority. Writer17
completed/read-only; Main freezes source through review. Fake/native disposable
tests only, no actual private reads/Git/network/cloud mutations. Stop immediately
on fingerprint/source drift, private input need, scope/role conflict. ACK
received/executing immediately with report_to=/root, heartbeat10-15min, blocker
immediate; final proactively send verdict/fullHEAD/exact dirty paths/tests/findings/
limits/external mutations and canonical LF fingerprints. Main remains active until
completion is received and handled. Review acceptance is not live import evidence.

Security30 REQUEST_CHANGES received/handled: completed import must parse equal
source/copy bytes as ASC private key before COMPLETE, not equality alone. Other
boundaries accepted,58 focused fake tests PASS; native not rerun by reviewer.
Writer17 completed handoff/read-only; Main takes its two paths solely for this
small correction and regression tests. Other four source/test files stay frozen.
No real custody operation; independent targeted rereview before commit/CI/import.

Security31 targeted rereview: same TASK/branch/base and advisor actor/claim,
lease_version=31, write=read-only, owned_paths=none, report_to=/root. Review only
completed-branch parser correction and invalid/equal-key regression in the two
key_custody source/test files; the other four retain Security30 fingerprints and
accepted scope. Immediate received/executing ACK, heartbeat10-15min, blocker
immediate, proactive final verdict/fullHEAD/paths/tests/findings/limits/mutations
and LF fingerprints required. No private/native/cloud/Git mutation. Main remains
active, frozen source pending rereview; old final status does not authorize import.

PR253 source717c603752b56e562ed9d368a89f20e0fa00128d: first CI34696504831
Windows job failed three native source-fixture tests at ACL_REJECTED; Ubuntu and
quality passed. Remaining run cancellation requested, not PASS. Fixture assumed
the Windows token's default object owner equals current user. Main makes only
fictional source directory/file ownership explicit via OWNER_SECURITY_INFORMATION,
retaining inherited DACL and all runtime guards. Local four native tests PASS;
fresh hosted CI remains required to verify the host difference is resolved.
Microsoft reference: https://learn.microsoft.com/en-us/windows/win32/secauthz/owner-of-a-new-object
and https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow

Security32 packet: TASK198, same branch, base/head717c603752b56e562ed9d368a89f20e0fa00128d;
actor/claim unchanged advisor, lease32, ownednone, write=read-only, report_to=/root.
Only delta tools/tests/test_ios_testflight_key_custody.py temporary native fixture;
production sources unchanged. Check exact local fixture-only Owner operation and
preserved DACL/runtime rejection. No private/Git/network mutations; fake tests
only. Immediate received/executing ACK, heartbeat10-15min, blocker immediately,
proactive final verdict/HEAD/hash/tests/findings/limits/mutations. Main active until
completion handled, frozen file during review, same PR/normal CI after acceptance.

## PKCS8 compatibility correction after zero-mutation key rejection

PR253 merged d9d2a4f5f4342891df6d30fea5aaf72ee34d5dfc after CI34696846257
SUCCESS16/16; local merged tree equals accepted552c623f4fd6f918ff9b2c667cae842f66ab57c5.
Actual reviewed preview ASC_IMPORT_READY; one import attempt KEY_REJECTED before
any backup/copy/update. Independent metadata-only checks confirm asc-upload.p8
and testflight-inputs.pre-import.json absent. Original six-field JSON/source
untouched. No signing/upload/Secret/runtime mutation. Do not repeat unchanged code.

Code-only fictional probe reproduces a compatibility bug: valid P256 PKCS8 with
the RFC5915 inner named-curve parameter loads to the same public key, but the
existing byte-for-byte serializer comparison returns KEY_REJECTED. This is not
proof of the real input's exact ASN.1 representation. Main may repair this bounded
parser behavior under IOS-TF-01 before any new attempt; no new Owner input yet.
Use only explicit encodings regenerated from the cryptographically validated key:
PKCS8 with inner P256 parameter present/absent and public point present/absent.
Retain full exact PEM/DER comparison against those finite encodings, size/curve/
private-key checks, key public/private consistency, no unknown attributes/trailing
bytes/extra PEM blocks, no key rewrite or normalization on disk. No broad ASN.1
acceptance, new algorithm, wire fields, authority, credential creation or cloud work.
Reference: https://www.rfc-editor.org/rfc/rfc5915.html section3; encoding-field
differences are not a reason to regenerate a user's key.

Checkpoint: goal=bounded PKCS8 interoperability; core=ios_testflight_inputs.py and
direct tests plus one custody integration regression; invariant=valid P256 private
key and finite exact envelope shapes only, no private input diagnosis/readouts;
tests=four fictional encodings plus malformed/extra/conflicting fields and full
affected tooling; ambiguity=actual real format unknown, no unreviewed retry.
Main claim/lease unchanged, branch codex/task-198-pkcs8-compatibility,
base=head=d9d2a4f5f4342891df6d30fea5aaf72ee34d5dfc. Main owns inputs/direct test,
key_custody direct test and existing five coordination records; agents read-only
unless separately assigned. Independent review and normal CI/merge required before
fresh metadata preview and one import; the approved copy has not happened yet.

Security33 assignment: same TASK198, branch codex/task-198-pkcs8-compatibility,
base=head=d9d2a4f5f4342891df6d30fea5aaf72ee34d5dfc; advisor actor/claim unchanged,
lease33, write=read-only, ownednone, report_to=/root. Three frozen files: inputs.py,
test_ios_testflight_inputs.py and test_ios_testflight_key_custody.py under tools.
Check finite four regenerated PKCS8 encodings, private/public consistency, curve,
unknown/trailing/extra-envelope rejection, reused shared Apple/ASC caller boundary,
byte-exact original copy and no-repeat behavior. No real inputs/network/Git/source
mutation; fake tests only. ACK received/executing immediately, heartbeat10-15min,
blocker immediate, proactive final verdict/fullHEAD/paths/tests/findings/limits/
mutations/LF hashes. Main frozen and active until review handled, then normal CI.
