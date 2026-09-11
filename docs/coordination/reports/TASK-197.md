# TASK-197 writer report

Main current scope: Owner approved one target-only rediscovery diagnostic, not a
signing retry or repair. Writer lease3 and independent security lease4 completed;
ACCEPT for one hosted observation only. Main expanded76 tests73PASS3platform skips,
reviewer39 tests38PASS1skip; Python quality and diffcheck PASS. Ten owned dirty paths
include the prior five closeout records and this substantive diagnostic delta.
Fixed --diagnose-identity never calls codesign; the workflow deliberately fails
the signing gate afterward. No merge, signing or private-operation authority.

Prior completed observation: source/security accepted, but native signing remains STOP.
PR250 is Draft/unmerged at4e22fa4c779a980dc86cf26a36eed71f27e09f14. Diagnostic
run34608233601/native103291939930 reports only identity-message match, NONZERO
exit and verified cleanup; no real assets/signing/upload. Independent evidence
assessment found no justified source remedy. Product archive job103291939983 PASS:
actual Runner.xcarchive built, IPA skipped, fixed archive/app identity/version and
unsigned checks succeeded, fictional configs removed. Archive not retained/uploaded.
Main requested cancellation of remaining CI after all in-scope new evidence;
cancelled/unrun jobs are not PASS. No merge or signing/private retry authorized.

Branch `codex/task-197-fictional-signing`; base/current HEAD
`bf7430023825ddbf0160515a02b1c24b8a653749`. Claim task-197-writer-20260911
lease1, actor /root/csr_writer, report_to=/root. Four owned files delivered dirty;
no commit/push. Main coordination/workflow changes preserved.

Main integration: branch/origin HEAD4e22fa4c779a980dc86cf26a36eed71f27e09f14;
base/main bf7430023825ddbf0160515a02b1c24b8a653749. Independent source reviews
ACCEPT; evidence review STOP. Main focused command covering fictional signing,
TASK196, CI contract, release pipeline and candidate inspector:74run71PASS3skips;
changed Python quality/diff PASS. Corrected hosted Linux/Windows tool jobs PASS.
At that earlier closeout only final5 records remained local dirty, no status-only
commit/PR/CI. Next scope must explicitly permit bounded target-only read-only
certificate association/identity rediscovery; no new raw logs, import/repair,
search-list/ACL/trust widening or real materials. No assumption of missing cert.

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

## Writer lease2: one bounded codesign observation

HEAD `e72d908c4ba8031866578bf8969b006254d00dc1`. Main reports native
run34607165386/job103288354085 compiled/imported successfully but case0 stopped at
codesign_exit; cleanup VERIFIED. This establishes only child failure, not an ACL
cause. Main separately owns old workflow-selector test correction and cancellation
of remaining CI; none of that is writer execution evidence.

Native stderr now uses a synchronous nonblocking pipe, retaining at most8193 bytes
to detect an8192-byte limit. Overflow remains failure. There is no background reader
or unbounded communicate buffer. Existing20-second process deadline and kill/reap
2-second bound remain; final pipe drain is bounded2 seconds. Interrupted reads return
to the deadline loop. stdout still goes to null; no raw data/path/hash/prose is emitted.

Fixed codesign_exit/codesign_output enums and8 boolean markers describe only known
text presence: internal-component, interaction, authentication, identity, chain,
format, permission and resource-fork wording. These observations do not determine
root cause. Markers can only be asserted for completed bounded capture. Python
validates exact keys/types/allowlists and SIGNING_VERIFIED additionally requires
ZERO/BOUNDED, besides existing tamper and cleanup success. ACL/import/command/
partition/trust and acceptance conditions otherwise unchanged.

Tests-first new schema test failed before implementation. New suite9PASS; combined
new+TASK196 suite28run26PASS2Windows skips. Output enums, sentinel/types, contradictory
overflow success, native source cap/nonblocking/kill-before-reap contracts and old
timeout/cleanup negative tests pass. Native pipe behavior is source-contract evidence
only on this Windows host, not a claimed actual Swift overflow/reap runtime test;
reviewed macOS execution remains necessary. Owned format/check and diffcheck PASS.
No remedy or cause inferred. Four owned paths changed, Main dirty paths preserved;
only fictional local temp tests, no real assets/native/Git/API/hosted mutations.

## Writer lease3: target-only rediscovery, no signing retry

HEAD `4e22fa4c779a980dc86cf26a36eed71f27e09f14`. Owner renewed one read-only
observation after the prior codesign NONZERO/identity-marker result; no remedy
or further codesign run is authorized. New fixed CLI `--diagnose-identity` performs
the same fictional setup/import and verified cleanup, then queries only the target.
Original `--rehearsal` remains unchanged in purpose/acceptance and retains3 cases.
Diagnostic mode uses one correct fixture import, no repeat/reimport/cert insertion.

Primary [Apple SecItem.h](https://github.com/apple-oss-distributions/Security/blob/main/keychain/headers/SecItem.h)
documents `kSecMatchSearchList` as limiting search to its supplied SecKeychainRef
array. Both certificate and identity queries supply exactly `[target]`,
`kSecMatchLimitOne` and `kSecReturnRef=true`. No default/global/DP/synchronizable,
policy/trusted/date filter or fallback query. This is the newly created file
Keychain reference, not a guessed path or general search list. Each result is
checked by CF type ID before casting; a certificate's DER and an identity's copied
certificate DER are compared only in memory with the expected fixture bytes.
The one-result limit is not an enumeration or uniqueness proof.

Only fixed query statuses NOT_CHECKED/FOUND/NOT_FOUND/ERROR and type/DER booleans
are emitted. Error, wrong result type or DER mismatch yields diagnostic inconclusive.
NOT_FOUND can complete observation but does not establish signing readiness.
Native IDENTITY_OBSERVED requires no codesign execution plus verified cleanup;
Python also rejects contradictory status/boolean/success combinations. A native
guard prevents crossProcessSign in diagnostic mode; the import diagnostic branch
never enters the signing branch. No extra write, ACL/partition/trust repair or
codesign invocation. All real/export/signing flags, including fictional_codesign,
remain false for diagnostics. Main explicitly keeps the hosted signing gate failed
after its diagnostic invocation; green observation cannot merge the delivery.

Tests-first new observation test failed before implementation; new11PASS, combined
new+TASK196 command30run28PASS2Windows skips. Tests cover found/not-found/error,
type/DER inconsistency, sentinel/schema, one diagnostic native call/no-sign mode,
cleanup and unchanged original negatives. Owned format/check and diffcheck PASS.
Swift query behavior remains unexecuted on this Windows writer host; native source
assertions are not runtime API evidence. Main reports separate workflow/pipeline
28run27PASS1skip; attributed to Main, not rerun by writer.

Four owned paths dirty; prior Main records preserved. External mutations only
fictional local temporary tests; public Apple documentation read. No real asset,
native Keychain, Git/API/hosted operation, remedy or new dependency. One reviewed
hosted observation remains; unsupported/inconclusive query stops, no additional
diagnostic or correction is authorized by lease3.
