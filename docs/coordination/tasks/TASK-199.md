# TASK-199: Account foundations without a release or UI freeze

Type: delivery; delivery_group: account-foundation-20260916; risk: L3 source only.
Base: d83bd4b1e64bad119f780344fbde6d57c378f308.
Branch: codex/task-199-account-foundation.
Main: /root; claim_id: task-199-main-20260916; lease_version: 1.

Status: completed, source delivery only. PR267 merged as
a8b10c3e9804dc89eb0459917580c02405d3dec3 after independent ACCEPT and16PASS;
main CI also16PASS. Exact tree matches approved publication commit. No runtime
rollout, real deletion or new store build. Main task claim and all delegated
claims released; remaining product/provider/privacy decisions stay open.
Five local closeout docs await the next substantive PR, not a status-only PR.

## Owner authorization and outcome

Owner approved all three boundaries of the four-hour package and explicitly
requested immediate execution on 2026-09-16. Implement and test useful account
foundations; preserve the Owner's undecided Flutter UX and first-release scope.
Existing branch/commit/public push/PR/CI/merge standing authority applies after
independent acceptance. Do not commit on main. Preserve the four Main-owned
TASK-198 post-merge records and include their reconciliation in this delivery.

This package permits source changes, isolated fictional test databases, SDK
inventory, privacy/support drafts, safe read-only staging checks and metadata.
No runtime deployment or migration, signing, upload, store action, true account
deletion, real user data, provider/key/Secret changes or new paid services.
The existing aggregate USD20 ceiling is not reset; unknown cost stops that run.
Private input/login/MFA stops that lane, not independent offline work.

## Execution checkpoint

1. Outcome: authenticated deletion-request foundation, auth/logout regressions,
   privacy facts and truthful support, plus correction of the wrong school name.
2. Core paths: Mobile API, shared mobile/portal-data modules and a compatible
   additive migration if necessary; Flutter account surfaces/tests; release docs.
3. Invariants: a request is never a completed deletion; no Person/Member/session
   deletion or provider revocation; no automatic live enablement. No policy,
   retention deadline, support identity or public URL is invented.
4. Evidence: architecture review before implementation; focused positive and
   negative tests including cross-person access, stale/revoked principal,
   concurrent/duplicate submission, malformed input, disabled mode, offline and
   uncertain client outcomes; affected suites plus required hosted matrix.
5. Limits: actual fulfillment, pending/restricted-account support, retention and
   true provider/device acceptance remain explicit future gates where absent.
   No speculative refactor or release-controller rebuild; no new device request.

## Accepted bounded deletion contract

Independent architecture ACCEPT received and handled from /root/native_upload_review,
claim task-199-account-review lease1 at base d83bd4b1e64bad119f780344fbde6d57c378f308.
Main accepts the contract below and releases backend implementation. This is not
source acceptance; final immutable source review remains required.

GET /api/v1/me/account-deletion returns200 {request:null|{id:UUID,
status:requested,requested_at:UTC-Z}}. POST exact {confirmed:true} and canonical
UUID Idempotency-Key returns202 the same envelope for first/duplicate requests.
The constant command is semantically idempotent per Person, without key hashes.
Request body is bounded; duplicate/unknown JSON keys and query args rejected.
Missing service or persistence failure returns fixed service_unavailable503 with
retryable=false; POST uncertainty always reconciles via GET, not auto retry.
No arbitrary Person/request ID; fresh self-auth checks precede any existing row.
Lock order follows existing admin/event, identity, Person, session boundaries;
clock sampled after locks. Pending/restricted identity access remains unsupported.
0013 compatibility is a Main-owned explicit consumer review, not blind replacement.
The migration adds only request receipts; any downgrade must preserve receipts
and cannot claim data restoration. Final rollout stays separately gated.

Main also owns the demonstrated SessionController generation races: five new
deterministic tests fail on old source (late refresh200/401, old200 response,
old401 retry as a new account). Serialize credential store transitions only,
invalidate generation before awaiting, bind refresh single-flight to generation,
check before/after network and use a distinct superseded exception; no new
controller, provider access or network lock. Add delayed-storage/logout races.

- Explicit optional service injection, absent in normal bootstrap. No change to
  default real capability projection or current live clients.
- Authenticated self-service request/status only, no user-supplied Person ID,
  no admin bypass, no free-text PII, no completion/erase/revocation executor.
- POST requires explicit confirmation and a UUID idempotency key. Recheck the
  active Person, identity and mobile session inside the write transaction.
- At most one pending request per Person, stable opaque request ID and fixed
  `requested` status; duplicate requests never imply deletion or generate work
  twice. GET is scoped to the current active principal, never arbitrary IDs.
- Client integration remains explicitly injected/fictional until the backend
  and fulfillment policy are approved. Do not expose a working-looking dead
  button in the current real app. Unknown outcomes reconcile via status, never
  silently resend. Offline is read-only, and no private contents reach logs.
- Final contract and accepted schema/revision implications are recorded here
  before writers implement. Migration is repository-only, not deployment.

## Assignment protocol

All assignments use COLLABORATION section 2 once: immediate received/executing
ACK with exact actor/claim/lease/report_to, heartbeat every 10–15 minutes,
immediate blocker, proactive completion with full SHA/dirty paths/tests/findings/
limits/external mutations. Main keeps its turn active and processes completion.
Reviewers are read-only and do not accept their own implementation.

### Architecture and later independent review

task=TASK-199; branch=codex/task-199-account-foundation;
base=head=d83bd4b1e64bad119f780344fbde6d57c378f308;
actor_id=/root/native_upload_review; role=advisor;
claim_id=task-199-account-review; lease_version=1;
scope=challenge the bounded deletion/auth contract before source implementation;
owned_paths=none; write=read-only; report_to=/root;
stop_conditions=missing authority, real credentials/data, external writes.

### Privacy facts and draft writer

task=TASK-199; branch=codex/task-199-account-foundation;
base=head=d83bd4b1e64bad119f780344fbde6d57c378f308;
actor_id=/root/privacy_foundation; role=codex-writer;
claim_id=task-199-privacy; lease_version=1;
scope=source-backed SDK/data inventory and clearly marked privacy/support drafts;
owned_paths=docs/releases/MOBILE_PRIVACY_DRAFT.md;
write=allowed; report_to=/root;
stop_conditions=unknown legal/policy choices, need for private input or publishing.
Read current lockfiles/native plugins/manifests without opening private config.
Use primary official documentation for SDK/store behavior; distinguish source
facts, archive evidence and unknown runtime behavior. Do not invent legal
retention or legal identity, and do not alter release gates. No Git mutations.

## Verification and integration budget

### Backend writer (implementation waits for architecture acceptance)

task=TASK-199; branch=codex/task-199-account-foundation;
base=head=d83bd4b1e64bad119f780344fbde6d57c378f308;
actor_id=/root/account_backend; role=codex-writer;
claim_id=task-199-backend; lease_version=1;
scope=bounded deletion-request service/persistence/API and their direct tests;
owned_paths=shared_lib/shared_module/account_deletion.py,
 shared_lib/shared_module/portal_data/account_deletion.py,
 shared_lib/shared_module/portal_data/models.py,
 shared_lib/tests/test_account_deletion.py,
 tests/portal_data/test_account_deletion.py,
 migrations/versions/0013_account_deletion_requests.py,
 apps/mobile_api/app.py,apps/mobile_api/openapi.json,
 apps/mobile_api/tests/test_account_deletion.py,
 apps/mobile_api/tests/test_openapi_contract.py;
write=allowed after Main records architecture acceptance; report_to=/root;
stop_conditions=architecture pending, overlapping edits, real data/credentials,
 runtime enablement, policy decisions or unapproved revision/caller changes.
First inspect current persistence/auth/test harness and propose the exact minimal
wire contract. No implementation until Main explicitly accepts the architecture.
Do not modify bootstrap, revision allowlists or unrelated tests without Main
coordination; Main owns cross-caller compatibility and Flutter integration.
No Git or external mutations; use patch and isolated fictional tests only.

### Revision compatibility writer

Privacy writer claim task-199-privacy lease1 completed; Main read/accepted the
132-line draft as a draft, not policy/compliance. That claim is now released.
The same actor receives only this new role; no concurrent privacy edits.

task=TASK-199; branch=codex/task-199-account-foundation;
base=head=d83bd4b1e64bad119f780344fbde6d57c378f308;
actor_id=/root/privacy_foundation; role=codex-writer;
claim_id=task-199-revision-compatibility; lease_version=1;
scope=explicit0013 consumer compatibility and isolated test harness integration;
owned_paths=apps/mobile_api/revision_readiness.py,
 apps/mobile_api/tests/test_revision_readiness.py,apps/mobile_api/README.md,
 apps/mobile_api/tests/test_app.py (revision-readiness mocks only),
 shared_lib/shared_module/portal_data/{identity_lifecycle,mobile_repository,repository}.py,
 tests/portal_data/{test_migration_readiness,test_event_guest_lifecycle,test_persistent_admin_authority,test_phase_c_readiness}.py,
 tests/portal_data/{_persistent_admin_authority_test_harness,_event_guest_lifecycle_test_harness,_account_deletion_test_harness}.py,
 tools/{portal_data_migration_readiness,portal_data_phase_c_migration}.py;
write=allowed; report_to=/root;
stop_conditions=need to broaden real operator authorization, nonlocal DB, overlap,
 private data or unreviewed behavioral changes. No Git/external mutation.
Preserve0012 behavior and fail closed on unknown/multihead; explicitly cover
Apple last-admin protection and event notification projections at0012/0013.
Do not advance exact production inventory/operator contracts automatically.
Coordinate new isolated cleanup helper with backend writer; no database startup.

One substantive delivery group/PR after independent source acceptance. Use
focused local evidence before expensive CI. Auth/model/migration/shared-boundary
changes use L2/L3 and the actual CI classifier, not the Flutter incubator shortcut.
No baseline smoke/device repetition. Defer runtime-only gates as explicitly
unverified; do not mark the whole IOS-TF-01 objective complete.

### Session pre-commit review

Architecture lease1 released. actor=/root/native_upload_review; role=reviewer;
claim_id=task-199-account-review; lease_version=2; report_to=/root;
base=d83bd4b1e64bad119f780344fbde6d57c378f308; branch as above;
scope=read-only targeted review of frozen dirty integration.dart and
session_race_test.dart, with caller inspection; owned_paths=none.
Main does not edit those two files until this finding pass completes.
No Git/external mutations or credential access. ACK received with exact fields;
same heartbeat/blocker/proactive completion protocol. This is not final immutable
source acceptance. Main continues independent parser/docs/test integration.

Lease2 completed REQUEST_CHANGES: queued clear/logout cleanup can be cancelled
by a new login and leave old local data; exceptional network exits lack the
generation fence. Existing12 tests pass but do not prove these two invariants.
Main accepts findings, releases review lease2 and requires RED-to-GREEN cases.

### Session corrective writer

Backend claim task-199-backend lease1 completed and released (source still subject
to final independent acceptance). actor=/root/account_backend; role=codex-writer;
claim_id=task-199-session-correction; lease_version=1; report_to=/root;
branch/base as above; owned_paths=clients/flutter_app/lib/integration.dart,
clients/flutter_app/test/session_race_test.dart,
clients/flutter_app/lib/basic_app.dart (session boot composition only).
Preserve existing Main title/deletion injection changes. Main freezes these paths.
Scope: resolve lease2 R1/R2 with deterministic old-data/new-data and failure tests;
cleanup is a publication barrier, never a late purge of a newer account. Network
exception paths must preserve same-generation classification and reject stale work.
No controller rewrite/new dependencies/Git/external mutations/private data.
Immediate ACK,10–15min heartbeat, blockers and proactive completion required.
Ask Main before widening callers. Final independent reviewer must not be author.

### Backend and revision source review

Revision writer claim task-199-revision-compatibility lease1 completed/released.
Main reviewed its core diff and accepts it for integration, not final acceptance.
actor=/root/native_upload_review; role=reviewer;
claim_id=task-199-account-review; lease_version=3; report_to=/root;
branch/base as above; owned_paths=none; read-only backend10 and compatibility16
source/test paths from packets above (frozen; Main may update README/docs).
Validate optional self-only service, transactional auth/dedup,0013 retained
migration,0012/0013 authority/Apple last-admin/notification behavior, unknown and
multihead rejection. Record LF fingerprints for later immutable commit binding;
source verdict does not replace mandatory hosted PostgreSQL15/16 evidence.
No Git/external writes/private data. Same ACK/heartbeat/completion protocol.

### Client request-flow review

actor=/root/privacy_foundation; role=reviewer; claim_id=task-199-client-review;
lease_version=1; report_to=/root; branch/base as above; owned_paths=none.
Prior compatibility writer role released. Review Main-authored frozen Flutter
account_deletion.dart/support_app_info.dart/production_demo.dart and
test/account_deletion_test.dart; only inspect basic_app optional injection/title
while session correction owns boot changes. No acceptance of own compatibility
or privacy work. Check confirmation/default-off/fictional/offline/uncertain and
cross-account semantics, strict JSON contract; record LF hashes for final binding.
No edits/Git/external/private access. Same ACK/heartbeat/completion protocol.

Client lease1 completed with uncertainty-provenance P2 and a settled-receipt
invalidation gap. Main accepted and fixed both; three RED tests now GREEN, with
six additional sequences and persona isolation. Session writer explicitly
authorized readonly generationChanges ValueListenable<int> and complete scoped
boot purge for this integration. Client reviewer same actor/claim now lease2,
same four frozen paths/protocol/stop conditions; rereview42PASS snapshot and bind
new LF hashes, never reuse old fingerprint acceptance.

### Final immutable review

Session corrective writer claim completed and released after27 race tests,
275 affected tests and analyze PASS. Main full Flutter395PASS/analyze clean.
Client reviewer lease2 ACCEPT after42 focused tests; backend reviewer lease3
ACCEPT with mandatory PG limits. Main may create the local source commit to
bind those snapshots; publication/PR follows final independent source acceptance.

actor=/root/native_upload_review; role=reviewer; claim_id=task-199-account-review;
lease_version=4; report_to=/root; branch as above; owned_paths=none.
Exact full commit is supplied from git rev-parse in dispatch packet, never
inferred from a short SHA. Inspect immutable SessionController/basic boot/
session_race_test correction and close R1/R2 plus notifier integration; compare
the25 prior backend LF hashes to Git blobs. Read updated rollout/privacy/state
docs for false claims, not as authority to operate. No source/Git/cloud/private
writes; same ACK/heartbeat/proactive completion. Source ACCEPT remains conditional
on mandatory hosted PG15/16 and normal CI for final merge, not runtime readiness.

Client reviewer same actor/claim lease3 was a binding-only read-only continuation:
all four lease2 hashes match immutable fae9f094cca00864ee541e158f0c7d5b6c8745a5;
ACCEPT returned proactively with correct parent/branch and clean tree, no repeat
tests. That claim is now complete/released. All current writers are frozen.

Final account reviewer lease4 ACCEPT bound to the same exact source commit,
R1/R2 closed and27 independent race tests PASS;25 backend hashes match. All
delegated claims complete/released, no unattended writer. Main accepts source
and proceeds to one ready PR/CI; merge remains conditional on hosted15/16 and
required CI. Only evidence/status docs may change without source rereview.
