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

## Main: corrected hosted result and stop

Exact pushed source `17733b31e724329551aa54ccf3bd2d54de12bbc9`,
[run34570308734](https://github.com/r06521541/NTUBTOB-management-system/actions/runs/34570308734),
native job103170839880. macOS15.7.9/build24G830 arm64, Xcode26.3/build17C529,
SDK26.2 observed. Native-host focused tests15 PASS; helper compiled; unsigned
fictional archive verified. temporary_keychain_verified=true proves all three
required correct/mismatch/wrong-password cases reached their expected result and
confirmed cleanup. Final cleanup_verified=true. The retained case2 AUTH_REJECTED /
OS_AUTH_FAILED / import detail is the expected wrong-password test, not evidence
of the later export cause.

Final classification=EXPORT_INCONCLUSIVE, stage=export,
manual_export_rejected=false. Export did not match the bounded expected-refusal
classifier; its exact underlying reason is unknown. No raw output recovery or
further native diagnostic was performed. positive_export_verified,
real_assets_verified, real_signing_authorized, signing_authorized,
upload_authorized and release_authorized remain false.

The authorized one source correction resolved custody-path admission, but did not
establish complete archive/export feasibility. The dedicated gate failed; PR249
is not mergeable under this task's acceptance contract and stays unmerged. Stop
after this bounded recovery; do not loosen predicates, retry Owner intake or
introduce real credentials. Further export investigation requires a new bounded
work scope. This local evidence update does not trigger another status-only CI run.

Full run34570308734 completed FAILURE: only the new fictional native job and its
CI final aggregate failed. All other selected jobs passed, including Android API36,
iOS Release no-codesign compile, Linux/Windows deployment tooling, PostgreSQL15/16,
service suites and quality. Local new+CI-contract tests32run29PASS3platform skips;
independent lease3 review ACCEPT and owned Python quality/diff checks PASS. Exact
local HEAD and origin task branch both match the source SHA above. Only four Main
closeout documents remain dirty (HANDOFF, PROJECT_STATE, task and this report);
no source changes or unrelated/untracked files. PR249 OPEN, autoMergeRequest=null.

## Writer lease4: Owner-renewed fictional export observation

HEAD `17733b31e724329551aa54ccf3bd2d54de12bbc9`; the preceding Main stop evidence
is preserved. Renewed authority permits this diagnostic only, not a speculative
remedy. Added fixed `export_detail` exit enums and independent marker booleans for
options/method/empty-methods, archive/single-bundle, team/accounts, profile/certificate,
permission/file and general export failure. Markers are lexical observations, not
root-cause determinations; overlapping markers are retained. Output remains bounded
in memory and no code number, stdout fragment, path or arbitrary value is emitted.
Timeout/process failure retains `NOT_RETURNED`; unknown text remains unclassified.

Fixed `archive_detail` reads only the newly generated archive's root/app Info.plist
with safe-path validation and65536-byte limits. It reports fixed parse statuses and
booleans for ApplicationProperties, exact expected ApplicationPath/bundle, archive
version, signing/team presence, app package type and Products/Applications shape.
Directory shape checks consume at most two entries per fixed directory; unrelated
names are never returned. Missing/malformed metadata is observation, not a new
acceptance rule. Existing `expected_export_rejection` and all native/ACL/trust code
are unchanged; unknown export still fails and positive export/real authority false.

Tests-first two new tests failed before implementation; final focused command
`py -3.10 -m unittest tools.tests.test_ios_xcode_feasibility -q`:17run15PASS2Windows
platform skips. Coverage includes all finite marker mappings, concurrent markers,
exit categories, invalid/oversized output, sentinel suppression, missing/malformed/
oversized plist, extra products/apps, and orchestration preserving inconclusive
acceptance. Owned Python format/check and `git diff --check` PASS.

No native/hosted/Git/API execution, real input or new dependency. Only fictional
local temporary test files were created/removed. Three owned paths changed; Main's
dirty coordination documents and appended report evidence preserved. macOS export
observation is pending independent review and Main's authorized diagnostic slice;
this delivery makes no claim about its underlying cause or a remedy.

## Main: renewed diagnostic result, no justified remedy

Exact source312263b92ad6e6e3d0cf366ded03cfe64972616c;
[run34576904526](https://github.com/r06521541/NTUBTOB-management-system/actions/runs/34576904526),
native103191375389. Hosted focused17 PASS; unchanged exact macOS15.7.9/24G830 arm64,
Xcode26.3/17C529 and SDK26.2. Fresh archive root/app metadata parsed; expected bundle,
ApplicationPath, app package, archive version and single-app Products shape matched.
SigningIdentity/Team absent as consistent with the unsigned fixture; absence alone
does not explain export behavior. All three custody cases and cleanup verified.

Export classification EXPORT_INCONCLUSIVE; exit SOFTWARE_ERROR (70), only
export_failed marker true. No listed specific marker matched. This is not evidence
excluding those error categories; exact Xcode failure remains unknown. Positive
export and all real-asset/signing/upload/release flags false. No raw logs/artifacts
recovered, Owner inputs requested or source remedy attempted. Reviewer independently
assessed Main's fixed evidence (not a second native execution) and agrees no
evidence-based correction exists. Do not modify metadata/method/ACL or broaden
success simply to use remaining correction budget.

Diagnostic design was insufficient to identify the actual export error. Next scope
should review a bounded fictional-only error-evidence channel before another run;
do not repeat the same markers or ask Owner to regenerate signing material.
Apple [TN3110](https://developer.apple.com/documentation/technotes/tn3110-resolving-generic-xcode-archive-issue)
informed archive-shape hypotheses only, not a claim of this failure's cause or a
guarantee of unsigned export. This result provides no such guarantee.

Local new+CI contracts34run31PASS3skips, quality and independent lease4 review PASS.
Before cancellation, hosted Linux/Windows deployment tools, Web/LINE/Notify/Game/
schedule services, PG16, quick/quality passed; PG15 and Android/iOS jobs were still
running. Main requested cancellation of the remaining run to avoid further cost
after conclusive diagnostic stop. Incomplete/cancelled jobs are not PASS. PR249
remains open/unmerged; five Main closeout records stay local, no status-only
commit/push/CI rerun. No private assets or product/runtime/provider operations.

Post-cancel readback: Android/iOS jobs cancelled; PG15 finished successfully during
cancellation. Main closeout-only dirty paths: HANDOFF, PROJECT_STATE, task, report,
review. Exact HEAD/origin both equal source above, no source/untracked changes;
PR OPEN/autoMergeRequest=null. `git diff --check` PASS (only CRLF warnings).
Final run status completed/conclusion cancelled; watcher ended. No background work remains.

## Writer lease5: bounded fictional error prose

Base HEAD `312263b92ad6e6e3d0cf366ded03cfe64972616c`. Owner renewed only error
evidence from the endogenous no-account fixture export. Added JSON data field
`fictional_export_error`: first `error: exportArchive` line plus at most two
immediately following nonempty indented lines, at most320 ASCII characters each.
Existing bounded process output stays in memory; lines over4096 characters become
a fixed oversized marker. No full log or artifact is produced.

ANSI CSI/OSC and remaining controls are removed. Paths, URLs, email, UUID,
credential assignments (including complete Authorization Bearer/Basic values),
long token-shaped strings, uppercase/alphanumeric10-character identifiers and
encoded-material boundary lines are replaced. Ordinary English prose is preserved
without a vocabulary allowlist. This is deliberately NOT a generic secret scrubber:
arbitrary natural-language sensitive values cannot be guaranteed detectable.
Use on real outputs is outside authority. Text remains inert JSON data, never
instructions, commands or acceptance evidence. Export acceptance and native/ACL/
trust/provisioning behavior are unchanged.

Tests-first new test failed before implementation. Final focused suite18run16PASS
2Windows platform skips; owned Python format/check and diffcheck PASS. Coverage
preserves prose, removes control/OSC text, checks standalone password/token/user/
path fragments (not only whole original inputs), limits count/length, rejects
oversized process output, handles no marker, and preserves unknown-export failure.
Main's interim Authorization residual-token finding was corrected before review.

Three owned paths changed; Main's existing report/coordination evidence preserved.
No real assets, native/hosted/Git/API execution or new dependency; only fictional
local temporary test fixtures. Actual Xcode prose remains unobserved locally and
requires independent review before Main's one authorized fictional observation.
No root cause or source remedy is asserted.

## Main: reviewed prose diagnostic awaits tool push gate

Local committed SHA337892c3a02f9759f9dd007bf7d3204be2621b9b; independent lease5
ACCEPT and Main35run32PASS3platform skips, two-Python quality/diff PASS. Branch
codex/task-196-xcode-feasibility; local origin tracking remains
312263b92ad6e6e3d0cf366ded03cfe64972616c. Push was rejected before execution by
auto-review. Read-only origin verification confirmed the exact previously approved
GitHub destination and no pushurl override; same direct retry with this evidence
also rejected. No workaround, no new hosted run and no actual error prose obtained.
Tool requires explicit renewed Owner confirmation of this reviewed batch/destination.
Stop with three Main status records dirty (HANDOFF/task/report), no source edits.
No real assets, signing, deployment, upload or repository visibility change.

## Writer lease6: exact observed fictional profile refusal

HEAD `337892c3a02f9759f9dd007bf7d3204be2621b9b`. Main-provided observation from
run34602920230/job103274382747:18 hosted tests PASS, archive/custody/cleanup true;
error prose reported no "iOS App Store" profiles for the redacted fixture team
matching the redacted fixture selector were installed. The old substring
`No profiles for` misses the intervening quoted profile type. This is evidence of
the intended fictional missing-profile refusal, not real profile validity or
positive unsigned-archive export capability. Main cancelled remaining diagnostic
jobs; cancelled/unrun work is not PASS.

Added one exact whole-line alternative bound to existing ExportOptions Team
`FICTTEAM01` and zero UUID selector, requiring the existing nonzero exit/output
bounds. No stripping, prefix/suffix acceptance or arbitrary "profiles" matching.
Existing three recognition alternatives are unchanged; options, signing, native,
trust and all external behavior are unchanged.

Tests-first regression reproduced false on the observed line. Final
`py -3.10 -m unittest tools.tests.test_ios_xcode_feasibility -q`:19run17PASS2Windows
platform skips. New positive full-line/log-context tests and negative wrong Team,
selector, prefix/suffix, partial line, generic failure and zero exit tests PASS.
Mocked orchestration verifies expected refusal plus cleanup, while positive export
and every real/signing/upload/release flag remain false. Owned Python format/check
and diffcheck PASS. No writer hosted/native/Git/API or real-asset operation; only
fictional local temporary test files. Three owned paths dirty, Main report/status
records preserved. This is the single authorized evidence-based correction; native
validation remains for independent review/Main. Persistent failure stops without
further diagnostic iterations.
