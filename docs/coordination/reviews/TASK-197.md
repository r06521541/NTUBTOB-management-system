# TASK-197 review

Status: independent source/security ACCEPT; native and merge acceptance pending.
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
