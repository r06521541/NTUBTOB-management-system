# TASK-197 writer report

## Current delivery: reviewed safe grouped diagnostic

Writer lease5 completed; independent security lease6 ACCEPT received and handled.
Main81 tests78PASS3skips; reviewer44 tests43PASS1skip; Python quality/diff PASS.
One hosted observation pending. Parent/fresh-child target-only queries, typed
key can-sign metadata and offline certificate checks only. Native policy remains
NOT_EVALUATED; codesign NOT_RUN, all real/signing authority false. PR250 stays Draft.

## Prior Main analysis: source-only identity selection

At98ca1fbdacf5e85f2bb379760152e481290925e8, Main compared the fixture and fixed
codesign arguments with Apple primary documentation and source. No product/tool
source changes, native run, hosted CI, private access, import, signing or Git/API
mutation. Public source/API reads only; five existing coordination files preserved.

- [Apple Code Signing Tasks](https://developer.apple.com/library/archive/documentation/Security/Conceptual/CodeSigningGuide/Procedures/Procedures.html)
  explicitly permits self-signed identities for internal tests. Lack of an Apple
  issuer is therefore not itself a diagnosis for this fictional Mach-O test.
- [Apple cs_utils.cpp](https://github.com/apple-oss-distributions/security_systemkeychain/blob/2b4c65b1074521e9c1dd2c8dc7fbf45dd775ec70/src/cs_utils.cpp#L183)
  is historical implementation evidence, NOT a version match to the runner binary.
  It searches with code-signing policy and SIGN key usage, then matches an exact
  40-hex SHA1 over certificate DER; generic policy is used to classify failures.
  The local Swift selector uses that same digest/input/hex form. No evidence for
  switching to CN, shortening the hash or removing the explicit target Keychain.
- [Apple SecPolicy.c](https://github.com/apple-oss-distributions/Security/blob/db15acbe6a7f257a859ad9a3bb86097bfe0679d9/OSX/sec/Security/SecPolicy.c#L2621)
  adds basic X509 checks, DigitalSignature-or-NonRepudiation KU and standard
  CodeSigning EKU. Our generator supplies DigitalSignature KU, CodeSigning EKU,
  nonempty subject, RSA2048 and SHA256 with fresh validity. This checks obvious
  generator settings only, not complete native policy/chain/trust acceptance.
- [Apple IdentityCursor.cpp](https://github.com/apple-oss-distributions/Security/blob/db15acbe6a7f257a859ad9a3bb86097bfe0679d9/OSX/libsecurity_keychain/lib/IdentityCursor.cpp#L105)
  distinguishes plain key-usage enumeration from policy-filtered enumeration;
  even non-valid-only policy searches can perform preliminary certificate checks.
  Do not treat a generic item query or find-identity valid-only count as an exact
  substitute for codesign's current internal selection behavior.

Evidence gap: latest observation uses the importing process and no policy filter.
It proves neither fresh-child visibility nor signing eligibility. Earlier
marker_identity combines general missing-item and missing-identity strings; raw
stderr was intentionally not retained, so exact original wording cannot be
recovered. Other markers being false does not exclude unobserved failure classes.
No root cause or repair justified by static analysis. No reason to add certs,
change KU/EKU speculatively, use trust-all, alter search lists or involve real keys.

Next proposed bounded package: collect same-process/child target visibility and
sign-usage/qualification evidence together with exact safe APIs and no signing.
API/network/global-search boundaries require review before any native execution.
This is a proposal, not a performed test or expanded authority. No tests rerun
because executable source is unchanged; final diffcheck is the document check.

Main current outcome: one target-only rediscovery completed; further work STOP.
Source/origin98ca1fbdacf5e85f2bb379760152e481290925e8; PR250 OPEN/Draft/unmerged.
Run34610163522/job103298388880: IDENTITY_DIAGNOSTIC_COMPLETE; both certificate
and identity FOUND, both exact expected DER and correct CF types, cleanup VERIFIED.
Codesign NOT_RUN/NOT_READ; every signing/export/real/release flag remains false.
Old19/new11 hosted tests PASS. Intentional diagnostic-only exit1 keeps the signing
gate failed. Main requested remaining CI cancellation; no full-suite PASS claim.
This disproves neither ACL nor tool-policy hypotheses, but provides no basis for
missing-certificate insertion/reimport. It proves fresh target first-result matches,
not uniqueness, cross-process visibility, earlier-run identity or root cause.
No repair, second observation, merge or private action in this renewal. Final5
coordination records remain local for next substantive work, avoiding status-only CI.
Final API read: run34610163522 completed/cancelled; watcher closed. HEAD equals
origin98ca1fbdacf5e85f2bb379760152e481290925e8; main unchanged at
bf7430023825ddbf0160515a02b1c24b8a653749. Only five coordination records dirty.

Pre-execution scope: Owner approved one target-only rediscovery diagnostic, not a
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

## Writer lease5: bounded parent/child selection observation

Base HEAD `98ca1fbdacf5e85f2bb379760152e481290925e8`; lease4 was revoked
before implementation. Fixed `--diagnose-selection` uses one fictional import,
plain target-only certificate/identity queries in parent and fresh same-executable
child, typed CFBoolean can-sign metadata and key target association. No native
policy query/trust evaluation/signature/codesign is added. Policy qualification
is always NOT_EVALUATED; all signing/real authority flags remain false. This
process-boundary observation is not codesign ACL or complete iOS signing proof.

Child opens only the existing fixed Keychain and receives public expected DER
(4096-byte maximum), never P12/password. It cannot create/import/unlock/delete.
Nonblocking pipes, ignored SIGPIPE, 4096-byte output cap, 20-second deadline and
bounded kill/reap protect parent lifetime; unreaped child prevents native
SecKeychainDelete. Outer controller still attempts task-root file cleanup and
reports cleanup UNRESOLVED. Nested output has exact keys/types and bounded8192
bytes. Failed child must have empty child data; UNREAPED cannot claim cleanup
VERIFIED. Native executable is canonical/current-user/mode0700 checked.

Offline certificate metadata uses existing cryptography only. `parsed` is the
completion indicator: false on parser/dependency failure, required true for
completed observation. Missing KU/EKU extensions are valid false metadata, not
parser success confusion. Apple policy is never inferred from these booleans.

Tests-first and final focused command:
`py -3.10 -m unittest tools.tests.test_ios_fictional_signing tools.tests.test_ios_xcode_feasibility -q`
ran35: 33PASS, 2 Windows platform skips (new module16 tests). Covers strict nested
schema, contradictory cleanup/child status, typed false can-sign, missing extension,
malformed DER, child failure/timeout, one import/no codesign, bounded/source IPC
contracts and unchanged old modes. Swift remains source-contract evidence only:
no native compile/runtime/Keychain execution on this Windows writer host. Main's
separate integration evidence is28run27PASS1skip, not rerun by writer.

Primary Apple SecItem.h defines target search-list/ReturnRef queries; SecKey.h
documents SecKeyCopyAttributes/kSecAttrCanSign; SecKeychain.cpp implements the
path-specific SecKeychainOpen. No policy/global fallback guarantee is inferred.
Only four owned paths changed; Main records preserved. No real assets, Git/API,
hosted or native mutation; local tests use fictional temporary material only.
