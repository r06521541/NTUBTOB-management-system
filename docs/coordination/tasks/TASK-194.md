# TASK-194: implement reviewed finite CMS compatibility

Type delivery; delivery_group cms-compatibility; L3.
Branch codex/task-194-cms-compatibility.
Base/HEAD c2e14164ace77a5691bbe17e8980b4bc97a26cbf.
Owner approved implementation of TASK193 on 2026-09-11. TASK193 design/security
lease1 ACCEPT is the architecture authority; its exact policy/table and invariants
apply without broadening. Design and carried TASK192 records join this one delivery.
Main /root main-work task-194-main-20260911 lease1; older claims completed.

## Execution checkpoint

Goal: implement SHA256/384/512 RSA and typed signed-attribute compatibility as designed.
Core: CMS verifier, fictional rehearsal and directly affected tests/intake integration.
Invariant: finite allowlist, same-byte/native signature/trust/profile/custody guards;
no true assets, third diagnostic, Secret, signing/upload or profile regeneration.
Tests: tests-first expected-delta corpus, genuinely signed full supported combinations,
focused affected suite, independent security review, hosted native/full gate.
Next gate: exact separately approved real verification only after software delivery;
Owner's profile may remain unsupported; do not infer its digest/OIDs from prior matrix.

## Scope and authority

Implement all TASK193 policy rows, including SHA2-with-RSA/legacy rsaEncryption
OID/digest consistency, absent/NULL receiver support, recomputed eContent digest,
unique required attributes, optional signingTime/SMIMECapabilities/AlgorithmProtection,
2..5 attrs, max32 capabilities, same-OID-only parameter normalization. No signed-byte
rewrites. Preserve original file/tree/cert/signer/time/no-decrypt/no-network-trust
boundaries and native signature/pinned-root/purpose/Team/App evidence.
SHA1/MD5/unknown actual crypto remain rejected; bounded capability metadata does
not negotiate algorithms. New rejection deltas include inconsistent/tampered inputs;
do not weaken negative tests merely to preserve obsolete success assumptions.

Fictional matrix must genuinely sign each supported digest x signature OID encoding
x absent/NULL parameters x optional attribute combination, and run native verification
on macOS. Use existing no-private CI rehearsal entry; do not change dependencies or
workflows unless Main identifies a substantive necessity and updates authority first.
No native trust-code/root-anchor changes anticipated. Main owns all coordination,
runbook/state and final review. Writer owns only:
- tools/ios_profile_cms_verification.py
- tools/ios_profile_cms_rehearsal.py
- tools/ios_profile_intake.py
- tools/tests/test_ios_profile_cms_verification.py
- tools/tests/test_ios_profile_intake.py
- tools/tests/test_ios_profile_verification_runner.py
- docs/coordination/reports/TASK-194.md

## Sole writer assignment

task=TASK-194; branch/base/head as above; actor_id=/root/csr_writer;
role=codex-writer; claim_id=task-194-writer-20260911; lease_version=1;
owned_paths=seven exact paths above; write=allowed; report_to=/root;
scope=TASK193 accepted policy implementation and fictional evidence;
stop_conditions=trust weakening/private exposure/scope expansion/native incompatibility
requiring unsupported policy. Mandatory COLLABORATION2 packet: immediate ACK,
heartbeat10-15m, blocker immediately, proactive completion with full HEAD/dirty paths,
tests/findings/limits/external mutations. Self-review/tests then read-only, no Git/API
mutation or true asset access. No new agent needed; Main keeps active tracking.
Independent final review and one full/native hosted gate before merge; standing Git
authority applies to Main, not automatic release of any private input.

## Independent final review packet (activate after writer handoff)

task=TASK-194; branch/base/head as above; actor_id=/root/task181_review;
role=advisor; claim_id=task-194-security-20260911; lease_version=1;
owned_paths=none; write=read-only; report_to=/root;
scope=complete implementation delta, approved policy, signed fictional matrix,
intake/runner fail-closed integration, custody/output/trust invariants and focused tests;
stop_conditions=private access, policy broadening or unverifiable evidence.
Main activates only after writer completion/read-only confirmation. Use the generic
COLLABORATION2 ACK/heartbeat/completion packet. No Git/API/native-live mutation.
Main owns the review record; hosted macOS remains required after local acceptance.

Writer lease1 completed/read-only; actual six changed owned paths exclude intake
source (shared preflight/schema already imported). Report records 50 tests: 48 PASS,
2 macOS skips; 408 genuine vectors and explicit frozen-base expected deltas.
Security lease1 is now active against current exact dirty implementation and Main
documentation; HEAD remains the base above. No code writes during review.

Security lease1 final ACCEPT; reviewer completed/read-only. Main full iOS security
suite: `py -3.10 -m unittest tools.tests.test_ios_certificate_preparation
tools.tests.test_ios_certificate_pair tools.tests.test_ios_certificate_packaging
tools.tests.test_ios_certificate_custody tools.tests.test_ios_profile_validation
tools.tests.test_ios_pkcs12_compatibility tools.tests.test_ios_profile_cms_verification
tools.tests.test_ios_profile_intake tools.tests.test_ios_profile_verification_runner
-q` =131 run,127 PASS/4 platform skips. CI classifier/workflow discover `test_ci_*.py`
=37 run,36 PASS/1 skip; five owned Python quality PASS. No source changed after review.
Main now integrates one PR under standing Git authority. Full/native hosted success
is mandatory before merge; no live/private verification release follows the merge.
