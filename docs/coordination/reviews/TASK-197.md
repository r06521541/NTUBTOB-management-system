# TASK-197 review

Main handled security lease6 ACCEPT and one hosted observation at
3b1be6a607c565fa4184aec3493ef527995fbf19, run34614766702/job103313871418.
SELECTION_DIAGNOSTIC_COMPLETE: parent/child exact identity and typed canSign=true;
offline checks true, cleanup VERIFIED; old19/new16 tests PASS. Codesign NOT_RUN,
native policy NOT_EVALUATED. Explicit gate exit1 prevents signing/merge acceptance.
No source remedy justified; one observation budget exhausted. PR250 stays Draft.
Runtime success does not prove timeout/overflow/unreaped branches, codesign ACL,
Apple policy qualification or actual signing. Reviewer/writer remain read-only.

Current design review (security lease5) corrected to REQUEST_CHANGES for native
policy filters. Main independently found identity+policy dispatch at SecItem.cpp
L2951-2958 precedes _FilterWithPolicy; advisor confirmed IdentityCursor's first
trustLite evaluation is not skipped by trustedOnly=false. Initial leaf-only
reasoning omitted this call path and must not authorize the implementation.
No code/native/CI change was made under that withdrawn writer lease4.

Corrected safe design ACCEPT: plain exact-target importing-process/fresh-child
queries; typed key capability metadata and Python offline certificate attributes.
No native policy/trust evaluation; native_policy_qualification=NOT_EVALUATED.
Main chooses this narrower supported method without enlarging search/real-asset
authority and disclosed that it does not complete the Apple policy dimension.
Writer lease5 completed; independent security lease6 ACCEPT received and handled.
Main81 tests78PASS3skips; reviewer44 tests43PASS1skip; quality/diff PASS.
One hosted observation authorized, native compile/IPC still unverified. Unreaped
child blocks native SecKeychainDelete, not outer task-root file cleanup; cleanup
remains UNRESOLVED. No native policy, signing or codesign equivalence claim.

Status: security lease4 scope executed once; signing and merge remain blocked.
Base bf7430023825ddbf0160515a02b1c24b8a653749.

Main integration evidence: workflow contract tests first failed on the missing
signing/archive steps, then passed 18 tests (17 PASS, 1 platform skip) after the
implementation. Python quality passed for the Main-owned contract test.
Local PyYAML is unavailable; no claim of successful YAML parsing yet. Hosted parser
and native evidence remain required, after independent review.

Product archive uses pinned Flutter 3.47.0 `build ipa --no-codesign`; upstream code
returns after archive creation and before IPA export when signing is disabled.
[Pinned Flutter command source](https://github.com/flutter/flutter/blob/3.47.0/packages/flutter_tools/lib/src/commands/build_ios.dart#L475)
This is a control-flow rationale, not evidence that our Runner archive succeeded.
The old fictional native checks move to the isolated fictional job, removing key
import from the product-build job without removing their test coverage.

Required final checks: named-tool ACL/identity binding, bounded process/path/input/
output handling, build-before-key, tamper rejection, cleanup on each failure class,
unchanged default/search list and strict no-real/no-provision/no-upload assertions.
Positive fictional signature and unsigned product archive are separate evidence;
full Flutter signing, Apple profile/export, device/provider and TestFlight gates
remain unresolved even if both controls pass.

Reviewer /root/task181_review, task-197-security-20260911 lease1, ACCEPT received
and handled by Main. Independently ran the new signing, unchanged TASK196 and CI
contract suites:45 run,42 PASS,3 platform skips; diff check PASS. No source blocker.
Verified narrow named-tool ACL/no setters, exact signing certificate binding,
precise tamper rejection, bounded cancellation/cleanup and separated no-key archive.
Main repeated the same45 tests and quality check for all3 changed Python files:PASS.
Native Swift/codesign ACL compatibility and archive shape are not yet established.

First hosted run34607165386 at e72d908c4ba8031866578bf8969b006254d00dc1:
new native Swift compiled, new8 tests PASS; case0 codesign_exit failed, cleanup
VERIFIED. Old native checks remained PASS. No positive signature claim.
An overlooked test used macos-latest text as a job selector, causing Linux and
macOS pipeline suite failures before product archive creation. Main reproduced
the exact IndexError and changed it to the stable named job parser and unsigned
IPA archive command. Expanded73 tests70PASS3skips/qualityPASS. This does not change
any runtime acceptance. Main requested cancellation of remaining CI after new
failure evidence; cancelled/unrun jobs are not PASS. One bounded native message
category layer split is now in progress, without ACL or success changes.

Security lease2 ACCEPT received/handled. Independent37 tests36PASS1skip; Main
expanded74 tests71PASS3skips; changed Python quality/diff PASS. Nonblocking stderr
has8192-byte cap plus overflow detection, deadline/reap bounds and no raw output.
Markers only denote bounded text matches, not causes. No native remedy or ACL
change; one diagnostic observation may proceed in the same PR250.

Diagnostic source4e22fa4c779a980dc86cf26a36eed71f27e09f14, run34608233601,
native103291939930: new9 tests PASS; case0 NONZERO/BOUNDED, marker_identity=true,
all other markers false; cleanup VERIFIED. No source remedy inferred.
Security lease3 evidence-only STOP received/handled: explicit file-Keychain import
and selector calculation agree with Apple API intent. Returned identity/cert and
private-key target association are proven by helper; certificate persistence and
target-only identity rediscovery are not observed. Do not assume they failed.
No justification to change ACL, selector, search scope, trust or reimport. Bounded
layer-split budget used; no guessed correction. Further observation requires a new
explicit bounded scope. Reviewer did not rerun native/tests for this evidence review.

Main verified archive job103291939983 PASS on the same source/run: actual Flutter
Runner.xcarchive built, IPA explicitly skipped, UNSIGNED_FLUTTER_ARCHIVE_VERIFIED;
archive identity/version/unsigned checks and config cleanup succeeded. Linux and
Windows tool jobs also PASS. Remaining CI cancellation requested after scoped
evidence; never count cancelled/unrun jobs as PASS. PR250 OPEN/Draft, unmerged.
No positive codesign/export, actual signing or TestFlight acceptance.

Final API read confirms run34608233601 completed/cancelled; no pending native work.

Security lease4 ACCEPT received/handled. Independent39 tests38PASS1platform skip;
Main expanded76 tests73PASS3skips, changed Python quality/diffcheck PASS. No actionable
finding. Exact target [SecKeychainRef], LimitOne/ReturnRef, type and expected DER
comparison support only a first-result/not-found observation; not uniqueness,
codesign policy or complete root cause. Skipping returned-identity/challenge in
diagnostic mode is acceptable: expected DER comes independently from the internal
fixture, and no current key-possession assertion is made. Original rehearsal stays
unchanged. ERROR/type/DER mismatch is inconclusive. Native guard prevents codesign;
workflow exit1 prevents successful diagnosis from becoming a merge/signing gate.
One hosted observation allowed; no correction/retry/real access. Native API not
yet exercised for this delta; source assertions are not runtime proof.

Main native evidence: source98ca1fbdacf5e85f2bb379760152e481290925e8,
run34610163522/job103298388880. Old19/new11 hosted tests PASS; new diagnostic
FOUND both certificate and identity with exact expected DER/type, verified cleanup.
Codesign NOT_RUN, all signing/export/private authority false. Job failure is the
intended DIAGNOSTIC_ONLY_SIGNING_GATE_NOT_SATISFIED exit1 after successful diagnostic,
not a failed query. No newly justified repair; stop after this approved observation.
No claim of global uniqueness, child-process visibility or codesign acceptance.
