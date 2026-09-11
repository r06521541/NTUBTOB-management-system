# TASK-195 architecture proposal

Design only, 2026-09-11. Base5848831772017a039bbcccfa68e75ac849f89236.
Main /root. No implementation, private input, native execution or external mutation.

## Finding and recommendation

Recommend an Xcode-owned candidate archive/export path, not another speculative
CMS allowlist patch. This changes the delivery gate; it is NOT a diagnosis or a
guarantee that the existing profile works. Owner must approve the new architecture
before implementation, and later approve exact private custody/signing separately.

The current verification already calls Apple's CMSDecoder and SecTrust. Our Python
preflight blocks earlier; the generic INPUT_REJECTED also covers Team format,
certificate DER/BasicConstraints and envelope size. None is isolated by the latest
result. Replacing CMS code alone cannot be presented as fixing that unknown failure.

TN3125 says profile internals are undocumented/changeable; modern Apple systems use
DER-Encoded-Profile rather than the traditional plist as their authoritative view.
Our ios_profile_validation.py checks XML, not that inner representation. Existing
outer CMS/chain and XML match evidence remains precisely that, never full Apple
provisioning validation. This is a claim/architecture limitation, not proof of the
latest error's cause. Do not implement another reverse-engineered inner parser.
[Apple TN3125](https://developer.apple.com/documentation/technotes/tn3125-inside-code-signing-provisioning-profiles)

## Options and disposition

| Option | Real effect | Disposition |
| --- | --- | --- |
| Keep finite verifier | Preserves current contract; real path stays inconclusive | Safe pause/fallback, not progress to TestFlight |
| Relax/replace preflight with generic native decode | Retaining predicates retains blocker; removing them changes crypto/attribute acceptance and can expose decryption | Reject as an unreviewed shortcut |
| Xcode manual-signing archive/export, then separate Apple processing | Uses supported app-level delivery tools; requires new private custody and signed artifact evidence | Recommended architecture, not yet executable |
| Automatic/cloud-managed signing | Different certificate/account/network lifecycle; may create/manage assets | Out of selected scope; no speculative new certificates |

CMSDecoder does not verify during decode; signer-status evaluation is distinct.
IsContentEncrypted is available after finalization, by which time decryption may
already have occurred. Thus retain predecode no-encryption/resource guards in the
existing core; do not replace it with raw `security cms -D` as a trust decision.
[Apple public CMS API](https://raw.githubusercontent.com/apple-oss-distributions/Security/main/CMS/CMSDecoder.h)

## Responsibilities and claims

| Layer | Required evidence / claim | Never infer |
| --- | --- | --- |
| Repository controller | exact commit/toolchain/target, bounded custody, output filtering, one-shot scope | profile validity from filename/download |
| Existing CMS/XML tools | constrained outer signature/chain and selected XML matching only; freeze as auxiliary | Apple's internal policy or inner DER validity |
| Pinned Xcode archive/export | exact manually selected signing material and candidate processed by the observed tool/version | all iOS devices accept it or Apple server accepted it |
| IPA inspector/codesign | exact artifact integrity, expected identity/entitlements/version, staging-only config | provisioning authority, login readiness or release permission |
| Apple Validate App / processing | actual, separately scoped result for the exact candidate | App Review approval or TestFlight distribution automatically |
| Device/product checks | install, launch, provider/session and actual feature evidence | production/public-release authorization |

Xcode Validate App acts on an archive and includes distribution-signing choices
and App Store Connect checks. It is not a read-only profile-byte API or guaranteed
offline operation. Use it as a separately approved Apple/account step; exporting
alone is not server validation. Apple describes Validate App as limited initial
validation, and upload/processing as later work.
[Validate archive](https://help.apple.com/xcode/mac/current/en.lproj/dev37441e273.html),
[Xcode distribution](https://developer.apple.com/documentation/xcode/distributing-your-app-for-beta-testing-and-releases)

## Proposed complete path (not execution authority)

1. Pin macOS image, actual Xcode/SDK/build version, dependency locks, exact source,
   iOS scheme, staging configuration, bundle/version/build and expected entitlements.
   Inspect Xcode's installed help for accepted export options; no guessed option names.
2. Before credentials, resolve/build code and rehearse archive/export orchestration.
   Establish whether that exact toolchain can export/sign a prepared unsigned archive
   without rerunning project/package scripts after key import. This is a feasibility
   gate, not an assertion already proven by `flutter build ios --no-codesign`.
   If it requires a different signed-archive/build-with-key workflow, return the
   changed exposure for review before any real credential is introduced.
3. Later exact signing gate: reuse the existing certificate/P12/profile if suitable;
   separately authenticate intended Team/certificate key pairing and fixed candidate
   identity. Profile fields are selectors, not trusted authority or shell/build input.
   Keep entitlements from reviewed source, not arbitrary profile-derived settings.
4. Use an isolated ephemeral runner, task-owned temporary Keychain/profile directories,
   explicit manual signing and fixed export destination. No automatic provisioning,
   certificate creation/revocation, broad login Keychain modification or unreviewed
   network access. Do not use `-allowProvisioningUpdates` or an automatic fallback.
   Review the exact Keychain import/unlock/signing APIs and access control in software
   rehearsal; never pass passwords via command line, logs or shell interpolation.
5. Produce one quarantined signed candidate; inspect it without changing existing
   default readiness markers. `--artifact-only` is integrity evidence, not ready/PASS
   for TestFlight. Unsupported/unmatched assets stop without repair or regeneration.
6. Remove temporary signing material and confirm cleanup classification. Only after
   exact candidate acceptance request the separate Apple validation/upload gate.
   Validation/upload requires its own least-privilege account/API custody; do not
   place an upload key in the signing job. On upload uncertainty reconcile the exact
   build before retry. Apple processing, tester distribution and device tests follow
   explicitly; none is bundled into today's design or next fictional work package.

Manual signing is an Apple-supported choice, but the UI may show invalid/expired
profiles; selection is not acceptance. All bundle targets must use the expected
signing identity; no UI-default auto-management is presumed safe.
[Manual signing](https://help.apple.com/xcode/mac/current/en.lproj/dev1bf96f17e.html)

## New custody and security decision

TASK190's public-certificate/profile-only memory verification approval cannot cover
P12/password/private-key use, profile/Keychain/derived-archive disk writes or app
signatures. Existing memory-only PKCS12 rehearsal does not prove temporary-Keychain
signing safe. A signing workflow must separately specify exact input channels,
allowed processes, private log/resultbundle suppression, runner access, retention,
cleanup on failure/cancel and manual reconciliation when the runner/controller dies.
Deleting a file is not proof of storage erasure. Never publish raw Xcode logs,
Keychains, profiles, private envelopes or archives automatically; even signed IPA
metadata may identify the developer and needs an explicit artifact-retention scope.

No declared SHA2/root policy in the existing core changes. Selecting Xcode as the
app-level authority deliberately delegates platform compatibility to that observed
toolchain; do not relabel its acceptance as our finite CMS-policy PASS. Any explicit
organization-wide weak-algorithm prohibition must be resolved before private signing,
not silently bypassed under a new name. No claim of offline revocation follows.

## Smallest useful next implementation package

If Owner selects this architecture, implement only the secret-free orchestration
and fictional custody feasibility package first: exact toolchain preflight; no-key
archive preparation; reviewed native temporary-Keychain fixture/import/cleanup;
strict manual export invocation and bounded safe output; candidate/cleanup state
machine plus rejection tests; one independent security review and one scoped native
hosted proof. No new private executable entry is released until all invariants are
verified and its exact custody has separate Owner approval.

Fictional certificates/profiles cannot prove a real Apple distribution export will
succeed. Positive real signing/export remains an explicit later gate, not a fake
fixture assertion. Test wrong targets, key mismatch, unsafe paths, oversized/output
sentinels, cleanup failure, cancellation, auto-provisioning refusal and no-upload.
If the secret-free feasibility work cannot establish the intended process boundary,
stop and report that precise design gap instead of requesting Owner trial runs.

Existing missing Apple provider/runtime, deletion/privacy, TestFlight/device and
readiness gates remain. ios_release_pipeline.py is simulation-only, not a hidden
live signing adapter; adapting it is future implementation. This proposal neither
unblocks those gates nor changes application authentication.

## Evidence and next decision

Inspected current intake/CMS/native/profile/pipeline/inspector and release checklist.
Read public Apple documentation, including official TN3125 Markdown (web renderer
unsupported; read-only HTTPS retrieval succeeded). No Owner assets or account read;
no code/native/CI execution or external mutation, only Main planning documents.
Next Owner decision: select Xcode-led architecture and authorize the bounded
secret-free/fictional implementation package above, or keep the current path paused.
This is not approval to retry the old profile command or start signing.
