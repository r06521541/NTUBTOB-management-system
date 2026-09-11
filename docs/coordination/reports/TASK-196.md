# TASK-196 writer report

Writer `/root/csr_writer`, `task-196-writer-20260911` lease1.
Branch `codex/task-196-xcode-feasibility`; base/HEAD
`5848831772017a039bbcccfa68e75ac849f89236`. Dirty handoff, no commit/push.

## Delivered boundary

New entry: `python -m tools.ios_xcode_feasibility --rehearsal`.
No credential, arbitrary path, project, upload or live-adapter arguments. It creates
a fixed, self-contained fictional Objective-C iOS project, not the product Runner.
macOS15 family, actual public OS build, Xcode26.3/build17C529 and SDK26.2 are checked;
installed bounded Xcode help must contain the selected manual-export keys/values.
The image alias is not an immutable OS pin. The actual host architecture is recorded.

Order: public native-helper compile and no-key archive first; verify fixed app bundle
and unsigned codesign result; generate fictional PKCS12 internally; run independent
temporary-Keychain success, certificate/key-target mismatch and wrong-password cases;
then manual export of the original archive without rebuilding/project scripts.
Temporary Keychain is already deleted before export. No positive export/signing
capability is inferred from this no-key refusal. Unknown export failures remain
EXPORT_INCONCLUSIVE; only bounded explicit missing-profile/certificate messages
qualify as expected refusal. Even CONTROL_VERIFIED_EXPORT_REJECTED retains
positive_export_verified, real_assets_verified, real_signing_authorized and all
signing/upload/release authority flags false.

Native import explicitly targets a fresh private task Keychain and current-process
SecAccess, never default/login or a search-list setter. Same-Keychain private-key
association, certificate bytes and an in-memory signature challenge are checked.
Default/search-list metadata is compared before/after; no keychain contents are
enumerated. Exact SecKeychainDelete runs after success and import/mismatch failure.
The directory must end empty. Private bytes/passwords use a bounded stdin frame,
not argv or disk P12 files. The native binary is an internal fixture transport,
not a reviewed entry for real assets.

Public Apple API/source evidence reviewed before implementation:
[import options](https://raw.githubusercontent.com/apple-oss-distributions/Security/main/keychain/headers/SecImportExport.h)
document explicit target-Keychain and initial ACL options;
[StorageManager](https://raw.githubusercontent.com/apple-oss-distributions/Security/main/OSX/libsecurity_keychain/lib/StorageManager.cpp)
limits automatic search-list addition to login/System names. This source reading is
not a substitute for the runtime metadata checks on the pinned hosted toolchain.

## Custody / resource handling

Generated project, build/archive/export paths and temporary Keychain use a fresh
0700 task temp root. Paths reject lexical traversal, symlink ancestors and canonical
escape; cleanup checks exact root identity, task prefix and system-temp parent.
No HOME override or claim that securityd is isolated by environment is made. Minimal
child environment excludes caller credentials/debug settings. Xcode/platform cache
internals are not claimed erased or comprehensively inventoried.

Child input/output/time are bounded. POSIX process groups are killed even when the
leader has exited; worker joins are bounded and live pipe locks are not closed.
No raw child logs/resultbundles/archives are emitted or uploaded. Native interruption
or uncertain cleanup stays CLEANUP_UNRESOLVED even if task files were removed.
Filesystem removal is not secure erasure; whole-controller hard kill remains an
unproven cleanup condition. No fallback/retry/build-after-key import is implemented.

## Evidence

- Tests-first initial module import failed as expected before implementation.
- `py -3.10 -m unittest tools.tests.test_ios_xcode_feasibility -q`:
  10 run,8 PASS,2 explicit platform skips (Windows symlink creation unavailable;
  POSIX descendant-group behavior requires macOS/Linux).
- Tests cover ordered controls, honest export refusal, wrong bundle/toolchain,
  cancel before/during custody, cleanup failure/uncertainty, traversal/symlink,
  output/timeout/sentinel boundaries, minimal environment, fixed native API target
  and no provisioning/upload. A test-only Windows Python environment supplement
  provides SystemRoot for fictional subprocess execution; production stays macOS.
- Two owned Python files: repository quality format/check PASS. `git diff --check`
  PASS. No Swift/native compile, actual Xcode archive/export or native Keychain call
  was executed on this Windows writer host.
- Main-reported integration evidence, not rerun by writer: existing affected iOS
  baseline131 run,127 PASS,4 skips after approved outside-sandbox fictional ACL run;
  initial sandbox16 ACL errors recorded. CI contracts38 run,37 PASS,1 skip and owned
  workflow-test quality PASS. Local YAML semantic parsing was unavailable.

## Handoff / remaining gates

Four owned additions only: Python rehearsal, Swift fixture, focused test module,
this report. All Main dirty coordination/workflow files preserved; existing CMS,
intake, profile, readiness and dependency files untouched. No real asset, account,
API/Git/cloud mutation or costly hosted run occurred; only public source research
and disposable fictional local test files/processes were used.

Independent review must precede the single dedicated hosted macOS gate. Actual
native API compilation, exact Xcode archive behavior and refusal category remain
unverified until then. A refusal cannot prove an unsigned production archive can
later export successfully without project code after key introduction. Positive
real signing/export and every private custody expansion require a separate exact
Owner decision; the unknown prior INPUT_REJECTED cause is not diagnosed or fixed.

## Lease2: bounded fictional native layer split

HEAD `67d4c348762b04e255f6e954b849dce9b9a4d9f3`, same branch/four owned files.
Main reports run34568143647/job103164413215: actual pinned toolchain and unsigned
fictional archive passed; custody returned CLEANUP_UNRESOLVED, no export occurred.
The previous native result was not observable, so this does not establish a cause.

Native output is now one fixed six-field JSON object: reason, phase, error_class,
cleanup, cleanup_phase, cleanup_error_class. Path basename/prefix/canonical/temp
binding and directory stat/owner/mode/type are distinct phases, as are identity,
certificate, key association/target, algorithm, sign and verify checks. Cleanup has
independent delete/search/default/file/directory phases so it cannot erase the
operation's failure evidence. OSStatus values map only to finite categories, never
raw numeric codes, descriptions, paths or material. This is instrumentation of the
same predicates/API order, not a source remedy or relaxed target/ACL/trust check.

Controller records fixed case index0(correct),1(certificate mismatch),2(wrong password),
checks the exact schema/enum/duplicate/size/cleanup consistency and still requires
the expected result and verified cleanup to continue. An operation rejection with
independently confirmed cleanup now remains CUSTODY_REJECTED plus cleanup=true;
unknown output/process failure, residual files or unconfirmed cleanup remain
CLEANUP_UNRESOLVED. Early NOT_CREATED cannot qualify as a successful native case.
No raw/partial native output is exposed. Timeout without a final valid protocol
result remains unknown; no diagnosis is invented from missing evidence.

Tests-first missing protocol API failed as expected. Final focused suite12 run:
10 PASS,2 existing platform skips. Coverage includes strict/sentinel/duplicate and
contradictory cleanup rejection, preserved import-failure cleanup, residual files,
and native-source phase allowlist. Two owned Python quality checks and diffcheck
PASS. No native/hosted/private/Git/API execution occurred in writer lease2.
Main's dirty HANDOFF/task files preserved. Independent review precedes one changed
hosted slice; only then may one evidenced source correction be considered. Persistent
blocker after that correction is inconclusive, not another diagnostic iteration.

## Main integration

Security review ACCEPT for source/fictional-hosted admission, no actionable findings.
Main reran new rehearsal+CI contract/classifier suites48run45PASS3platform skips,
three changed Python quality PASS and diff check PASS. Dedicated macOS15/Xcode26.3
job uses locked existing dependencies, read-only token, no persisted checkout token,
no Environment/Secrets/artifact uploads; old product compile job is unchanged.
One delivery PR includes preceding Main TASK194 stop and TASK195 design records.
No real credential authority follows software integration.

## Writer lease3: one evidenced OS-temp binding correction

Base HEAD `29df9e3527628cd6555379c324d2ef916433cfb4`. Main-provided hosted
run34569286534/job103167763448 reached case0 `PATH_REJECTED/temp_binding`, with
`NOT_CREATED` and controller cleanup verified. This proves the old equality failed,
not whether Foundation environment handling or path spelling caused it. No Keychain
creation/import/export was reached.

Apple's [secure temporary-file guidance](https://developer.apple.com/library/archive/documentation/Security/Conceptual/SecureCodingGuide/Articles/RaceConditions.html)
specifies the user temporary directory and private subdirectories, using
`confstr(_CS_DARWIN_USER_TEMP_DIR)` at POSIX level. Apple's
[Libc header](https://github.com/apple-oss-distributions/Libc/blob/main/include/unistd.h)
defines that constant as65537; [Python3.10 os.confstr](https://docs.python.org/3.10/library/os.html#os.confstr)
accepts its integer value. No swift-corelibs implementation is treated as proof of
shipping Darwin Foundation behavior.

Python now allocates only beneath the canonical existing OS-returned directory,
not environment-selected tempfile defaults; cleanup revalidates the same authority.
Swift queries that OS API into a fixed4096-byte buffer, rejects failure/truncation,
and requires canonical path components of `cwd.parent.parent` equal that OS root.
The immediate hierarchy remains `task-196-*/custody`; canonical/symlink and custody
owner/mode/type checks remain, with explicit owner/mode/type checks for the task
root too. There is no caller override, broader-root fallback, or Keychain/API change.

Tests-first regression failed on the old missing OS-root contract, then passed.
`py -3.10 -m unittest tools.tests.test_ios_xcode_feasibility -q`:15run13PASS2Windows
platform skips. New coverage includes trailing separator normalization, bounded/
invalid OS response, lookup failure before allocation/process, environment TMPDIR
independence and wrong-root cleanup refusal. Native assertions are source contracts,
not macOS execution evidence. Owned Python format/check and `git diff --check` PASS.

Only four owned paths changed; Main HANDOFF/task dirty changes preserved. No real
assets, Git/API/hosted mutation or native Keychain execution. Public documentation
was read and fictional local temporary test directories created/removed. Native
compile/import/export remain unverified locally; independent review precedes Main's
one changed hosted slice. If the same blocker persists, stop inconclusive without
another diagnostic/correction iteration. Positive export and real authority remain false.
