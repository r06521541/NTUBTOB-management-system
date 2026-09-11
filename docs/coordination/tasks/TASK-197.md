# TASK-197: prove fictional signing and Flutter archive preparation

Type delivery; delivery_group ios-fictional-signing; L3. Owner approved preparing
the actual Flutter unsigned archive and testing a named signing process with only
internally generated fictional keys. No real certificate/P12/password/profile,
Apple account, provisioning, upload, distribution or production operation.
Fictional codesign is NOT Apple export, device acceptance or TestFlight readiness.

Branch codex/task-197-fictional-signing; base/initial HEAD
bf7430023825ddbf0160515a02b1c24b8a653749. Preserve the five Main-owned TASK196
closeout files and include them in this substantive delivery. Main /root holds
task-197-main-20260911 lease1, main-work; all TASK196 claims are completed.

## Execution checkpoint

Goal: actual Flutter no-key archive plus bounded fictional cross-process signature proof.
Core: new signing rehearsal/native helper/tests; Main workflow integration.
Invariant: all build/dependency code finishes before key import; only named Apple
signing tool afterward, explicit temporary Keychain, no default/search-list changes.
Tests: success/negative/cleanup/output/command boundaries, independent security review,
then one native observation and existing required final CI.
Unknown: narrow ACL codesign access and actual archive preparation; one bounded
layer split plus one evidenced correction per runtime blocker, no guessing loop.

## Scope and acceptance

Reuse existing bounded helpers without modifying TASK196 behavior. New CLI accepts
only fixed rehearsal action, no arbitrary private/project/profile inputs. Generate
fictional material internally; compile helper and fixed non-executed Mach-O fixture
before import. Only /usr/bin/codesign may join native trusted-application ACL.
No trust-all import, broad partition-list changes, login/default Keychain change,
automatic provisioning, passwords on argv, real assets or raw child logs.
Prove endogenous certificate/signature binding, tamper rejection, wrong password/
certificate rejection, and cleanup/default/search-list preservation. Do not execute
signed fixture code. Outputs finite/bounded; no private-shaped artifact upload.
Required broader ACL/partition/trust-store modification is a stop, not a fallback.

Main adds actual Flutter staging:real Release archive using fictional configuration
and CODE_SIGNING_ALLOWED=NO in the no-key job. Check app identity/archive shape and
unsigned state. Do not upload archive. These separate proofs do not establish full
Flutter nested-bundle signing or positive Xcode distribution export; state the gap.
Existing intake/CMS/private entry/readiness remain frozen. One independent security
review precedes expensive hosted work. One PR; standing Git authority covers
commit/push/PR/CI/merge at existing exact origin, not real signing/store mutation.

## Writer packet (COLLABORATION section 2 protocol applies)

task=TASK-197; branch=codex/task-197-fictional-signing;
base=bf7430023825ddbf0160515a02b1c24b8a653749;
head=bf7430023825ddbf0160515a02b1c24b8a653749;
actor_id=/root/csr_writer; role=codex-writer;
claim_id=task-197-writer-20260911; lease_version=1;
scope=fictional cross-process codesign fixture, cleanup and negative tests;
owned_paths=tools/ios_fictional_signing.py,tools/native/ios_fictional_signing.swift,
tools/tests/test_ios_fictional_signing.py,docs/coordination/reports/TASK-197.md;
write=allowed; report_to=/root;
stop_conditions=real inputs, broad ACL/partition/trust changes, arbitrary live inputs,
unbounded output, existing custody/intake changes, unsupported native authority.
No Git/API/hosted mutation. Immediate received/executing, heartbeat, proactive final
packet to /root then read-only. Main owns workflow/contract tests and task/review/
HANDOFF/PROJECT_STATE integration and clients/flutter_app/ios/README.md clarification.
Independent review activates after writer handoff.

## Independent review packet

Writer lease1 completed/read-only; Main received and handled completion. Main
45 tests: 42 PASS, 3 platform skips; quality PASS. No native execution yet.
task=TASK-197; branch=codex/task-197-fictional-signing;
base=bf7430023825ddbf0160515a02b1c24b8a653749;
head=bf7430023825ddbf0160515a02b1c24b8a653749;
actor_id=/root/task181_review; role=advisor;
claim_id=task-197-security-20260911; lease_version=1;
scope=complete frozen implementation/workflows/docs, architecture/security and tests;
owned_paths=none; write=read-only; report_to=/root;
stop_conditions=private access, unsupported authority or unsafe claim/scope expansion.
Mandatory protocol applies. No Git/API/hosted mutation. Review narrow process ACL,
certificate binding/tamper, process cancellation/cleanup, output taxonomy, actual
archive/no-key job separation and remaining real-export limits before hosted gate.

Security lease1 ACCEPT received/handled; reviewer read-only. Main resumes integration.
The reviewed source may enter one Draft PR for missing macOS evidence; mark ready
and merge only after native results and required CI acceptance. No private operations.
