# TASK-198 review

## Current signing-input classification: Security34 ACCEPT

Main received and handled proactive completion from /root/task181_review,
claim task-198-security-20260911 lease34; completed/read-only. Branch
codex/task-198-signing-input-reasons; base2ae97b339e542eeea766489dffdcd21aa45cfef6.
All binding acceptance predicates preserved; Team/date split retains original
order and short-circuit rejection. Fixed stages contain no values or raw causes.
Intake propagates allowlisted reasons only; generic errors remain sanitized.
Actual fictional encrypted P12 positive and wrong-password/malformed/key-kind/
certificate/Team/time/purpose negatives pass; operator rejection creates no
journal/session/inventory or repeat collection. Independent73focusedPASS/0skip,
diff clean. Main225tests221PASS4platformskips; quality/compile/diff PASS.
No findings. This repairs classification, not the Owner's material or password;
P12_DECODE_REJECTED alone cannot distinguish wrong password from invalid P12.
No private/native/network/Git/source mutation by reviewer, no real signing proof.

Accepted LF-SHA256:
- tools/ios_testflight_signing.py ec4218aab75def455461962dcd5ebf64d2c5cee20073833f586d2a4617989026
- tools/ios_testflight_intake.py 7f20d52c611f6e7d0f31c5ca1d05297296bfc5b60dfe08a3efd9c883e08c8c00
- tools/tests/test_ios_testflight_signing.py 6dc71c70913b9b2bdd94b86e53ac71ff612ceabea65643fefed0d017a5c48c49
- tools/tests/test_ios_testflight_intake.py 274f4ad5ca96518e0cff167b7af9b2ca1f4f76ad0c2ad94de62c40a9a432fe6c
- tools/tests/test_ios_testflight_operator.py c9f2ba46fd68f5aa75a8af8cd786a5c08f77869ff11506bb8b895da5ce11ad00

## Current PKCS8 compatibility repair: Security33 ACCEPT

Main received/handled /root/task181_review completion, claim/actor unchanged,
lease33, read-only; base d9d2a4f5f4342891df6d30fea5aaf72ee34d5dfc and branch
codex/task-198-pkcs8-compatibility. Three frozen inputs/source/direct-test/custody
test files independently accepted;22 focused fake tests PASS, no new findings.
Four exact candidate PEM encodings regenerated from a validated P256 private key,
with independently derived public consistency, do not admit unknown fields,
versions, trailing bytes, extra blocks, BOM, wrong curve or conflicting public.
Existing newline handling only; copy remains byte-exact. Shared ASC/AppleLogin
caller type/key-reuse boundary unchanged. Main218tests214PASS4platformskips.

RFC5915 section3 ASN.1 marks fields optional, while producer text says inner
parameters MUST and public point SHOULD be included. This finite receiver support
includes the former serializer's no-inner-parameter form; it does not claim all
four are fully RFC-conformant producer outputs or prove the actual private input
is one of them. No real private/API/native/Git/source mutations by reviewer;
only fictional test and Python cache. Hosted CI and live outcome remain unverified.

Accepted LF-SHA256:
- tools/ios_testflight_inputs.py c498c8a5195cb17e5525287140b4df3a0d1fd92e1db6bdaf73a2a8e3c946fde9
- tools/tests/test_ios_testflight_inputs.py 12daef970b7fcb59cb2a969ee3e7cc2815ae8d9aee258ed5f1eb3d4fa1ec5b0f
- tools/tests/test_ios_testflight_key_custody.py 96babd9528b1bb3a8b78f377ff946e847f750510c372d8cd1c293cb1922cb45a

## Previous ASC custody repair: Security31 ACCEPT

Main received/handled Security30 REQUEST_CHANGES then Security31 ACCEPT from
/root/task181_review, claim task-198-security-20260911 leases30/31, read-only.
Base/full HEAD b428ab9d25702c0c7516db11e0c20030f09591d6, branch
codex/task-198-asc-private-custody. Only finding: equality in existing-copy completion
did not establish valid private-key bytes. Main reproduced with a red test, then
added original ASC parser after one same-handle read of source/copy and equality;
invalid matching bytes, wrong curve or public-only PEM stop unresolved with zero
writes. Valid completion reparses, verifies custody, never recopies.

Other Security30 boundaries accepted: exclusive original settings handle,
CREATE_NEW protected exact metadata backup before copy/update, original source and
other five values preserved, source-only inherited-ACL exception with current Owner
and original type/link/size/path guards. Partial state retains files and stops;
no atomicity claim or automatic restore/delete/retry. Preview is metadata-only
PRESENT/READY, not cryptographic completion. Four upload assets are metadata/ACL
checked before password; actual signing/intake guards and authority stay intact.

Independent58 focused fake tests PASS then targeted10 fake tests PASS. Main final
215tests211PASS4platformskips includes four native Windows temporary fixture tests
outside sandbox; reviewer did not rerun native. Normal CI/merge still required.
No real private reads/copies/network/Git mutations by reviewer. Key syntax and
copy equality do not establish ASC server key purpose/permissions or history.

Accepted canonical LF-SHA256 for source intake/operator/key_custody respectively:
- 8db088aed24a0afceeb8159d2eddbfbf6e9db55accb1ca78568af4217feb6152
- 75b10dcf06ae8a5edfed44ac8fe74fd80727660a65e4da4c719feeb7ca2d771c
- 14b211126b5bce395c531ed95d31c9d04eafebe8543166cbe2aa084ff3c302c3
Corresponding three direct tests:
- 559b36598f31395fba0e252b0ffd588cb32ffa862df88018ba6ce393b460a0d2
- f3b34ded38a4f338291815faf0a3c8d55fe3c7a8488b200c463f8d1ed44bda8a
- ee903dd74f573222e0702d13567571bd41953074294439340e21d08a9c829f7f

Security32 test-only ACCEPT received/handled after PR253 Windows job rejected
three source fixtures with ACL_REJECTED. Source remains unchanged. Fixture now
sets only Owner (SE_FILE_OBJECT/OWNER_SECURITY_INFORMATION, DACL/SACL flags absent)
on its two fresh temporary source paths; keeps wrong-owner/hardlink rejection.
Independent4 native fictional tests PASS, Main215tests211PASS4skips. The new test
LF37347d98fdb707f2b6df65abed12a786511077d358b7ad03e13354fd23d12f09 supersedes
the test_key_custody fingerprint above; other five unchanged. Prior failed CI
34696504831 cancelled/superseded, not PASS. Fresh hosted CI still required;
fixture correction does not prove a unique host root cause without that evidence.

## Previous input-recovery repair: Security29 ACCEPT

Main received/handled /root/task181_review completion, report_to=/root, lease29.
Base/full HEAD48232c548d486c8175ac990dd91d2f68d218544b; branch
codex/task-198-private-input-recovery, six frozen source/test dirty files below.
No actionable findings. Owner-approved six-field metadata JSON is not a secret
cache or authority. Fixed private KnownFolder target, protected Owner CREATE_NEW,
same-handle write/flush/readback, no overwrite/ACL repair; load retains original
canonical path/reparse/type/linkcount/size/ACL/identity checks. Duplicate/unknown
fields rejected. Prepare/check do not read keys or dispatch; execute-settings
preserves fresh preflight, original journal/one-shot and hidden P12 password.
Balanced outer quotes stripped once; field-only syntax correction bounded3,
EOF/interrupt/file/crypto failure never retried; fixed output only.

Independent focused suite47tests:46PASS plus one sandbox fixture ACL setup error;
that exact native fictional template test was rerun with scoped escalation,1PASS.
47 distinct tests have passing evidence; do not call the sandbox run fully green.
git diff --check PASS. Main full191tests187PASS4platformskips, six-file qualityPASS.
Limits: SETTINGS_READY is syntax/custody, not cryptographic/ASC identity validation;
no actual Owner JSON read, signing/upload, CI or cloud mutation by reviewer. Hard
termination can leave partial template requiring Owner handling; no auto overwrite.
Same-user/admin memory access is outside ACL protection; password never persisted.

Accepted LF-SHA256 for tools/ios_testflight_{intake,operator,settings}.py:
- intake d51b45504a18287f313d334e7f4ede5fc7bc8362559f65b957545db9f016e381
- operator 29061a57824bf52376db6adc41238ee47fd26357a6ccef456fa1e887d6cfc2ac
- settings 1bdabffd8c1eab80b0d0a1b65d21fdd3601cde2932678e5303868cb36733fd7e
Corresponding tools/tests/test_ios_testflight_{intake,operator,settings}.py:
- intake 7a6580eae0664153c761f988128367adf0452cf44c81e2d75fae24a848a51e45
- operator b0832e8f5926eff8e0d612597409850cd08fcfab494a5b809231c70931eab79f
- settings ddf4626f3c44096a92a516b8f57c06adf0cec8697b0f0eadb84593b59cfbd73b


## Latest source review state

Final hosted acceptance of code-only checkpoint: run34636911592 SUCCESS16/16 at
2007016fa0bdd18bcfd2c546800e52a7ca477bbc, matched localHEAD/origin/PR251. Ubuntu
fixture correction now passes both hosted tooling platforms; current native compile
and unsigned iOS archive passed. No live signing/custody/receipt-handoff/distribution
claim. PR remains Draft, no merge. That checkpoint was doubly disabled.
New uncommitted activation/operator/journal/recovery delta is not covered by that CI.
Security23 ACCEPT recovery architecture, security24 ACCEPT journal/dispatch/recovery
with28 independent fake tests. Security25 REQUEST_CHANGES: normal failure needs
exact-run cancel plus bounded fresh observation/cleanup, and staging preflight
needs retained runtime/Secret/database ownership evidence rather than Ready/name.
Security26 ACCEPT received/handled: both prior findings resolved,42 independent
focused PASS/no skips. Six LF hashes matched frozen operator/dispatch/staging and
tests; accepted alongside prior security25 unchallenged source scope. Main166tests
162PASS4platformskips,workflow18tests17PASS1skip,quality16Python/diffPASS. No private
dispatch before fresh CI/merge. Both agents completed/read-only; Main integrates.
The new environment setup is complete and read-only verified, not an Owner blocker.

Security27 ACCEPT Windows executable-resolution delta14 independentPASS, including
real fictional .cmd spawn (no shell=True; batch interpreter semantics remain).
Security28 ACCEPT single-container name normalization28 independentPASS; executable
fields and ownership guards remain bound. Main actual read-only metadata verifier
returned STAGING_OWNERSHIP_RETAINED, not a reviewer live/schema/function claim.
Main169tests165PASS4skips,quality4Python/diffPASS; final normalCI still needed.
Pushed8a37459d2bcca32bb002605b0816a3d3c1c693dc CI34644785015 SUCCESS16/16.
Later correction push blocked by execution auto-review before any command ran;
these accepted dirty corrections still need hosted validation, not another code review.

Code-only run34630386472 on3484115c64080679bb58e1eedf6d3df8afc98282 completed
SUCCESS16/16, including native supervisor compile/input rejection. No real custody.
Source leases12/14/15/16/17/18 ACCEPT: upload exact ASC resource membership,
private IPA/leaf/profile binding, existing Windows ACL/handle intake, finite wire,
phase custody/owned cleanup, and current SPM dependency preparation respectively.
All synthetic/offline; actual Apple storage operations, Keychain/Xcode discovery,
POSIX cleanup and new SPM resolver output remain live/platform evidence limits.
Security19 REQUEST_CHANGES on ambiguous retention_resolved semantics; Main changed
to distinct current_absence_verified plus retention_resolved requiring no HTTP
uncertainty. Both PUT and DELETE timeout tests preserve unresolved retention even
after absence proof. No mutation or protection weakened.
Security20 accepted the retention correction but REQUEST_CHANGES: pending/valid
remote receipt had no durable handoff before automatic deletion. Main disabled
both workflow and hosted live entry and refuses deletion of nonempty receipts.
Security21 ACCEPT for dormant-checkpoint safety, not completion of the missing handoff.
Independent25tests24PASS1POSIXskip; three frozen source digests match. Both agents
completed/read-only and Main received/handled completion. Main final104TestFlight
tests101PASS3skips and18workflow tests17PASS1skip; diff/quality PASS.
New source is not an executable release controller; live acceptance remains open. Current
Main aggregate102 tests99PASS3skips/quality16Python PASS/diffPASS. No live or final
delivery acceptance; complete local operator and Owner distribution remain absent.
Environment bootstrap writer12 stopped without code after official API control
gap; Owner visible setup is required, then existing strict readback. Old profile
environment read-only GET confirms can_admins_bypass=false; it was not changed.

## Historical review evidence

Security22 ACCEPT test-only path semantics correction on checkpoint171efa870767f2aac161497a402d23869d24176a.
Fictional Windows custody now uses PureWindowsPath on every test host; _path
guards remain exercised with relative/parent/extension/ADS negative cases.
Independent10testsPASS; LF a77524e9854ab987992775f83de984a797ef514f1319dc8510d6ce0f276d5938.
No product edits/skips or live/native/API actions. Ubuntu corrected evidence subsequently
passed in final run34636911592 on2007016fa0bdd18bcfd2c546800e52a7ca477bbc.

Security architecture lease1 ACCEPT received/handled by Main at
3b1be6a607c565fa4184aec3493ef527995fbf19. Advisor source/public documentation only;
no tests/native/private inputs. Real execution remains subject to source review
and actual private intake, not another generic approval from Owner.

Accepted supported path: Xcode manual signed archive -> manual export -> private
artifact inspection -> separate ASC upload/processing -> exact Owner-only group.
Apple manual-distribution and archive guidance:
https://help.apple.com/xcode/mac/current/en.lproj/devcac6ab5b3.html
https://help.apple.com/xcode/mac/current/en.lproj/devff5ececf8.html
No dependency on arbitrary unsigned archive export or fictional codesign success.
Reviewed build phases execute within key window; dependency setup precedes it.
No auto-provisioning/new certificate/global key ACL; no public raw logs/artifacts.
Only platform processing proves Apple receipt, and only device evidence proves
installation/core flow. Keep source/public-ready and device claims separate.

Readiness advisor confirms existing profile controller accepts only certificate
and profile, not signing/upload keys. Existing lifecycle pipeline is simulation.
Staging build already bypasses public marker after external-signing checks;
artifact-only inspection can support internal delivery without fake marker PASS.
Actual internal release controller and credential custody still need implementation.

First slice security lease2 ACCEPT received/handled. Independently28 tests27PASS/
1platform skip, diff PASS. CLI nonzero still fails; no continue-on-error or true
signing flags. DEC-109/task limits faithful to Owner scope. Marker/public gate
unchanged; private profile presence not validity; no live controller claim.
Main repeated28 tests27PASS1skip and changed-Python quality PASS.
Native/hosted validation pending for this delta; real signing/TF not complete.

Main hosted acceptance: run34618189006 on8066ea54fbe4fd53bf01b06d46756550271cef57
completed SUCCESS, all16 jobs PASS. PR250 merged5762a89c6e6451ed19f5151da1652312a9f76679.
Both trees exactly2eb7e7893574fd4621e1e2db08ecfa46a692e270. No real credentials,
sign/upload/runtime mutation; platform diagnostic/archive are accepted as those
claims only. Full IOS-TF-01 remains incomplete.

Main2026-09-12 read-only follow-up: Owner login completed; existing App capability,
certificate/profile and ASC upload key visible. Developer Sign-in-purpose Keys
list empty. Owner subsequently approved one App-bound Sign-in-purpose key. Main
prepared the final Register draft; Owner now reported downloaded and portal confirms
the approved key was created/downloaded. Agent did not register/read/download keys.
No real signing/upload or new implementation acceptance.

Security advisor lease3 ACCEPT received/handled: supported discovery route permits
only ephemeral hosted-user temporary search-list insertion with exact preservation,
restoration/readback, unchanged default and own-Keychain cleanup; not global login
or trust-all. Main adopted scoped exception in task under IOS-TF-01 flow adjustment.
Profile uses Xcode26 current UserData location, create-exclusive/owned cleanup.
References verified by Main:
https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications
https://developer.apple.com/forums/thread/812538
Native access compatibility and actual signing remain untested. No native/private
execution during architecture review.

Input source security lease4 ACCEPT received/handled at base/HEAD
5762a89c6e6451ed19f5151da1652312a9f76679 plus the two frozen new source files.
Independent command: py -3.10 -m unittest tools.tests.test_ios_testflight_inputs -q;
9 PASS. No blocking findings. Main matched canonical UTF-8 LF SHA256:
- tools/ios_testflight_inputs.py:
  4a54fb22f67800b215abe44c8bd8a159bb269871341438c33c3b2fe285e8cbe3
- tools/tests/test_ios_testflight_inputs.py:
  6e1826bf9ec1a25939e410da31dc84e0e3dad25b94e19521258552c88cf986cf
Scope: separated memory types/P256 keys, fixed ES256 TTL/signature, RSA pairing,
structural profile binding and non-disclosing error categories; authority false.
Limits: password-required P12 parsing is not proof of all private bag encryption;
CMS/inner DER/Apple chain/revocation, provider/API key metadata and live custody,
native signing/upload remain unverified. Controller must enforce these boundaries,
including distinct keys; repr suppression does not authorize generic logging.
No private reads/native/source/Git/cloud mutation by reviewer; now read-only.

Transport architecture security lease5 ACCEPT received/handled; source-only,
no tests/private/native/external mutation. Accepted first-party step-only ingress
exception and separated children, not a claim GitHub runner lacks ASC input
before upload (environment secrets are read at job start). Main verified:
https://docs.github.com/en/actions/reference/security/secrets
https://developer.apple.com/videos/play/wwdc2025/324/
Future controller must bind source/run/nonce/expiry, refuse existing secret names,
bound each secret below48KiB, clean all attempted names and reconcile uncertainty.
Native cleanup plus independently bound private IPA must precede upload child.
Before upload verify no other internal group's automatic distribution exposes
candidate to another tester. New protected environment and actual wrappers remain
unimplemented; no live-readiness/Apple processing/Owner availability claim.

Signing-adapter source lease6 ACCEPT received/handled at current HEAD
c50a497aee7860b6de6f12584e0eb4d9bf7883ea plus three frozen new files. Independent
10 focused tests PASS; private frame/cert pairing, structural profile container,
temporary user-keychain search-list and owned cleanup/failure classifications
accepted as source only. Native compile, ACL/Xcode success and real custody are
not yet proven; cleanup VERIFIED excludes retained private artifact/DerivedData.
Code-only compile/rejection test and existing workflow addition lease7 ACCEPT;
reviewer test correctly skips on Windows. Main29 tests27PASS/2platform skips and
changed-Python quality PASS. No private/native/external mutation by reviewers.
Main adopted two bounded pre-live corrections: do not assume export basename,
and explicitly set/read finite idle locking on only the newly created Keychain.
Apple API warns nil target selects default; correction must use nonnil own target:
https://developer.apple.com/documentation/security/seckeychainsetsettings(_:_:)
No claim that idle-lock interval is hard destruction or actual native evidence.
Writer lease4 correction is pending and will receive independent delta review.

Correction lease8 ACCEPT received/handled. Independent13 focused PASS, canonical
hashes matched: signing Python ad0e6e98c1c2159d12a2a63ed73905e8b30f39751bc56310d4fa64fd8c2373e2;
Swift02b9475ba5d30664194c7a4a89cac8140cfdc154de27678d5076377d6ba8d5e6;
signing test fd878f5dacf0ceacac22ff7f485526a050b2121d7db1881b82c4fd49e5b30838;
workflow77c1e02e0fbc05cf85016793addd5f4f658f48ae8260c5e5677f19f3ac8cde55.
Native test unchanged899d460a5b3933fa83333c089e7bc2202b648fac320c4bc4956efaf292517a8b.
No unresolved source findings for code-only hosted compile gate. Mocked POSIX
metadata/hash-mismatch tests do not prove a real TOCTOU race or native settings;
idle timeout is not hard destruction. No real/private/native/external mutations.

Darwin source/diagnostic correction lease9 ACCEPT received/handled. Two focused
tests PASS; nullable spawn handles and per-success-init defer cleanup match
platform source without command/policy changes. Compiler diagnostics only apply
to public source before private inputs, not a general secret sanitizer.
Swift LF1b2c808af4b8803d994886cbbb09c50a5c402d7f613d3a151dd6619cbdfb272e;
native test e779981ec1c7431e5ee2e05c987282c00610caf0935488e448d4dde25701c416.
First job failed compile and lost actual error behind warnings; this acceptance
does not claim the sole root cause or native success. Corrected hosted evidence
remains required. No native/private/external action by reviewer.
