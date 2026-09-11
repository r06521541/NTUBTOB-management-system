# TASK-197 writer report

Branch `codex/task-197-fictional-signing`; base/current HEAD
`bf7430023825ddbf0160515a02b1c24b8a653749`. Claim task-197-writer-20260911
lease1, actor /root/csr_writer, report_to=/root. Four owned files delivered dirty;
no commit/push. Main coordination/workflow changes preserved.

## Implemented boundary

New fixed entry `python -m tools.ios_fictional_signing --rehearsal` has no private,
project, keychain or tool-path arguments. Reuses TASK196 bounded process/toolchain/
path helpers without modifying them. OS-user-temp private task197 root and custody
directory retain canonical/owner/mode checks. Compile native helper and a minimal
macOS Mach-O before generating/importing keys; the fixture is never executed.

New internally generated RSA2048 self-signed CodeSigning certificate has an aware
current-time validity window and no Apple markers/chain or remote URLs. Its P12 is
encrypted in memory; no plaintext key/password file or password argv. Python cannot
guarantee memory zeroization. Temporary persistent Keychain material is fictional.

New native helper carries forward explicit Keychain import, key association,
default/search-list snapshots and verified deletion. The sole added trusted
application is `/usr/bin/codesign`, alongside the current helper; there is no
trust-all, partition-list, login/default/search-list or trust-store mutation.
Codesign receives the exact fixture certificate SHA1 selector and temporary
Keychain, fixed identifier and `--timestamp=none`. SHA1 here is a selector/requirement
format, not the fixture certificate's signature algorithm (SHA256).

Only this fixed Apple child runs after import. Its output goes to null (no raw
logs), timeout20 seconds then kill/reap bounded2 seconds; unresolved termination
remains cleanup uncertainty. Native static validation disables network access,
checks the signature against the leaf fingerprint requirement, and separately
requires exactly one signing certificate with exact expected DER. It mutates one
byte of the unique known fixture data marker without executing it, then requires
`errSecCSSignatureFailed`, not an arbitrary failure. Wrong certificate/password
cases must return their exact categories and each confirm cleanup.

Six-field native details remain fixed allowlists. SIGNING_VERIFIED additionally
requires tamper_rejected/OS_SUCCESS and verified completed cleanup; contradictory
success is rejected. Top-level fictional_codesign_verified requires all3 cases.
Every positive-export/real-asset/signing/upload/release authority flag stays false.

## Evidence and limits

Tests-first initial import failed before implementation. New suite8 tests PASS;
new+unchanged TASK196 suite command:
`py -3.10 -m unittest tools.tests.test_ios_fictional_signing tools.tests.test_ios_xcode_feasibility -q`
reported27run25PASS2Windows platform skips. Coverage: encrypted fixture/key binding,
fixed CLI/no disclosure, success/negative/timeout/cancel/cleanup boundaries,
compile failure before key generation, command ordering/no fixture execution,
native API/source constraints and contradictory/malformed result rejection.
Owned Python format/check and `git diff --check` PASS. No native Swift/codesign
execution was possible on this Windows writer host; source tests are not native
runtime proof. Narrow cross-process ACL compatibility remains an explicit hosted
question; broader ACL/partition/trust changes are a stop, never fallback.

Main separately reports18 workflow tests17PASS1platform skip. Its actual Flutter
unsigned archive work is distinct from this minimal macOS Mach-O signing proof.
Neither their combination nor fictional signature success proves full iOS nested
bundle signing, positive distribution export, device acceptance or TestFlight.
Independent security review precedes native hosted observation; runtime recovery
budget remains one bounded layer split and one evidenced correction per blocker.

Primary references read:

- [Apple SecAccess.h](https://github.com/apple-oss-distributions/Security/blob/main/OSX/libsecurity_keychain/lib/SecAccess.h): explicit trusted application list controls confirmation-free access; system defaults may vary.
- [Apple requirement language](https://developer.apple.com/library/archive/documentation/Security/Conceptual/CodeSigningGuide/RequirementLang/RequirementLang.html): certificate leaf hash constraint; trust is distinct, not asserted here.
- [Apple SecStaticCode.h](https://github.com/apple-oss-distributions/Security/blob/main/OSX/libsecurity_codesigning/lib/SecStaticCode.h), [CSCommon.h](https://github.com/apple-oss-distributions/Security/blob/main/OSX/libsecurity_codesigning/lib/CSCommon.h): static validation flags including no-network; the explicit raw flag mask0x20000011 corresponds to documented no-network/strict/all-architectures bits.
- [Apple SecCode.h](https://github.com/apple-oss-distributions/Security/blob/main/OSX/libsecurity_codesigning/lib/SecCode.h): signing-information certificate array after validity checking, not a trust-store modification.

External mutations: only local fictional temporary test files created/deleted;
public documentation read. No real assets, native Keychain execution, Git/API/
hosted/provider action, deployment or new dependency by writer.
