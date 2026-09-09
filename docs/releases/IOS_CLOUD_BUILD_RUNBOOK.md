# iOS cloud build: rehearsal now, live Owner gate later

TASK-183 implements the **secret-free rehearsal**, not a live signing/upload
operator. Existing hosted macOS CI still compiles staging/real with fictional
configuration and `--no-codesign`; it cannot produce an installable candidate.
No paid runner, service, Secret or Apple resource is created. Public repository
standard hosted runner compute is currently free; artifact storage/retention and
future plan changes need separate budget checks. Do not select larger runners.

## Separate gates

| Phase | Current evidence | Not authorized by success |
| --- | --- | --- |
| Source compile | Existing hosted no-codesign build | Signing, install, provider readiness |
| Lifecycle rehearsal | Fixed in-memory scenarios | Live operation or reusable approval |
| Artifact integrity | Inspector `--artifact-only`, actual macOS verification of an existing IPA | Upload, tester distribution, public release |
| Live signed build | Not implemented here; future reviewed wrapper/Owner gate | Upload or public release |
| Upload/Apple processing | Not performed; future exact IPA/target/one-shot gate | Automatic tester distribution or App Store submission |
| Device/provider evidence | Owner iPhone and isolated staging required | Production readiness |

Default inspection retains its readiness guard. Artifact-only checks the same
bounded snapshot, archive, version/build, signature, bundle, minimum iOS,
distribution profile and Apple entitlements. It returns `ARTIFACT_VERIFIED`,
with `upload_authorized=false` and `release_authorized=false`. Even legacy
default inspection PASS does not grant upload authority. Never change the
readiness marker to unlock inspection or substitute contract-test evidence.

## Rehearsal (no private input)

```powershell
py -3.10 -m unittest tools.tests.test_ios_release_pipeline tools.tests.test_ios_candidate_inspector -v
$candidateCommit = git rev-parse HEAD
py -3.10 -m tools.ios_release_pipeline rehearse --expected-commit $candidateCommit --checkout-commit $candidateCommit
```

Hosted expected commit comes from `github.sha`, checkout commit from Git. A
mismatch stops before simulated staging. This check is not review acceptance
or approval. Scenarios cover partial staging failure, build failure, rejected
artifact/upload, uncertain upload, pending processing and failed cleanup.
Everything, including resource cleanup and attempts, is an in-memory simulation:
**it does not prove real keychain cleanup, network timeout handling or Apple
acceptance**. No live adapter, execute option, private reader or upload command
exists. Existing hosted source compilation is separate evidence.

## Approved future design, not execution permission

Owner approved a narrow exception to the generic private-environment/files ban:
a separately reviewed signing workflow may use protected GitHub Environment
Secrets and ephemeral hosted-runner keychain/necessary private files. Private
material must never reach chat, source, logs, caches, public artifacts or PRs.
This exception does not cover arbitrary helpers or self-hosted/shared runners.

Before implementing/activating the live path:

1. Verify exact Apple team/App/bundle and isolated staging without raw identifier
   output. Owner reported App ID/capability and App Store Connect record created;
   this delivery did not verify them. Do not create replacements from stale docs.
2. Review a pinned manual-only workflow, exact reviewed SHA and protected
   Environment rules. PR/fork/untrusted code never receives secrets; no
   `pull_request_target`, PR artifacts as release inputs or automatic signing on
   merge. Default `contents: read`; dependencies/actions pinned.
3. Approve custody: certificate/private key/profile and upload API key are
   distinct. Use minimum roles. Team API keys span all apps; do not claim
   single-app restriction or automate with Account Holder credentials. Owner
   controls one-time key download and secure backup.
4. Approve exact bootstrap wrapper/private-input mechanism. Use dedicated
   temporary storage/keychain, no shell tracing/raw output, no private caches,
   cleanup including partial staging in `finally` plus hosted `always()`. Never
   alter a persistent user keychain. Runner disposal is defense in depth, not
   evidence that cleanup succeeded.
5. Build/sign once and inspect on the same runner. Preserve approved sanitized
   evidence and separately approved private artifact handoff only. A public
   Actions artifact is **not** an approved IPA store. No private job outputs.
6. Separately approve one upload for exact IPA digest/version/build/App. Timeout
   or interruption means uncertain, not zero mutation: read-only reconcile in
   App Store Connect before any new approval. Pending processing never triggers
   reupload. Cleanup failure requires security review.
7. Keep provider, privacy/deletion, staging ownership and tester-release gates
   explicit. Merge does not grant any blanket release approval.

Group Owner identity confirmation, signing custody and minimal upload-role
choice into one preparation session. A personally owned Mac is not required;
Windows local CSR creation has a separate reviewed operator below; it is not
provided by the cloud rehearsal. Certificate import/conversion and live cloud
signing are still not implemented by that operator.

## Windows local CSR preparation (TASK-184)

The certificate-preparation operator is a separate local-only boundary, not the
cloud rehearsal or upload adapter. Owner reports the upload API `.p8` is safely
saved; it must not be read or replaced by this operator. The earlier empty
Certificates report is superseded by Owner's subsequent issuance report.

The local tool prepares one RSA-2048/SHA-256 certificate signing request and its
passphrase-encrypted PKCS8 private key. The CSR carries its common name/email;
it is not a secret key but still must not be pasted into chat/logs/repository.
Only the CSR is subsequently submitted by Owner to Apple. The encrypted private
key and its passphrase stay private; the upload API `.p8` is a different key and
cannot substitute for the certificate's matching private key.

The repository entry is `python -m tools.ios_certificate_preparation
--expected-commit <reviewed-full-SHA>` (read-only by default). Use Python 3.10
with the isolated pinned requirements in `tools/requirements-ios-certificate.txt`;
do not change service dependencies for this operator. A later exact Owner
release permits adding `--execute` to that same command. Never pass private
values as arguments or use a redirected input file. Do not run it from an
unreviewed/dirty branch.

The fixed output location is the Windows-native LocalAppData known folder plus
`NTUBTOB-AppleDistribution-CSR`. Output filenames are `distribution.csr` and
`distribution-private-key.pem`. The tool resolves the known folder itself, not
an arbitrary path supplied in chat; it refuses an existing output directory.
When prompted, common name is a label for the signing key; email is your chosen
certificate request address. Encryption passphrase is a **new password you
choose for this file**, not your Apple login password. Retain it securely and
separately from the encrypted file. Confirm the exact displayed commit only
after reviewing the fixed local action and filenames.

Before actual operation, Owner must approve the exact reviewed commit and the
creation of these local durable files. Implementation/test authorization does
not execute the real operation. Input is hidden in an interactive local console;
no email/name/passphrase arguments, environment values or saved transcripts.
Redirection/non-interactive input must fail, not silently reveal input. A clean
exact checkout, supported dependency/Windows host, new local non-reparse output
and verified restrictive ACL are prerequisites to key generation.

Input does not show characters while typing; after Enter, only the accepted
length is displayed. Final confirmation is the fixed `CREATE CSR` phrase plus
the displayed full commit. Results are `preflight_passed` (no creation),
`pre_execution_rejected` (fix/check before trying a new preflight),
`confirmed_success` (do not generate again) or `uncertain` (stop and preserve
partial output; no automatic retry). Opening a normal personal terminal may be
necessary: restricted agent sandboxes can deny Windows ACL writes. Do not
relax the ACL or rerun a real uncertain operation outside sandbox as a workaround.

The storage directory must not be a shared/synced/network/repository path. ACL
restriction is not protection against malware running as the same Windows user,
administrators or device loss; use a trusted personal computer and secure
offline backup. Python immutable objects cannot guarantee memory zeroization.
Do not lose the passphrase: there is no recovery mechanism. No plaintext key
export, private backup/upload or certificate conversion is performed here.

If cancellation or a write error occurs after directory creation, preserve the
protected partial output and stop. Do not delete, overwrite or regenerate just
to get a green result. A later read-only reconciliation/Owner decision is needed.
Actual Apple acceptance of the CSR, certificate download, matching certificate
validation, PKCS12 conversion and cloud provisioning remain separately reviewed
steps; a locally valid CSR does not prove Apple accepted it.

References: [Apple CSR instructions](https://developer.apple.com/help/account/certificates/create-a-certificate-signing-request/),
[Apple classic CSR format](https://developer.apple.com/forums/thread/699268),
[cryptography serialization](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/serialization/).

## Certificate/CSR correspondence preparation (TASK-185)

`tools.ios_certificate_pair` is an in-memory validation library, not a live
file-reading operator. Existing pinned certificate-tool requirements apply.
It accepts only bounded single public certificate/CSR byte objects and an
explicit timezone-aware verification time. Tests generate fictional material
in memory; no Owner key, saved API `.p8`, CSR or downloaded certificate is read.

The checks cover RSA2048/SHA256 CSR signature, corresponding public keys,
certificate validity interval and rejection of an explicitly CA certificate.
Missing BasicConstraints remains unknown, not evidence that a certificate is
qualified for distribution. Success is only `PAIR_MATCH_ONLY`.
Fixed STOP reasons distinguish invalid input/encoding/time/dependency, unsupported
CSR algorithm, invalid CSR signature, not-yet-valid/expired certificate, mismatched
public key and rejected CA. Unexpected failures remain `PAIR_CHECK_REJECTED`.
These categories contain no raw subject, dates or parser text, and do not grant
automatic regeneration/retry authority.

This deliberately does **not** verify certificate signature/Apple chain,
revocation, Team/App identity, certificate distribution purpose or provisioning
profile. It also does not establish that the private key is still available or
decryptable. Self-signed fictional certificates can pass correspondence; all
trust/possession/signing/upload/release authorities remain false. A future
reviewed bounded Owner wrapper must obtain actual public files safely before
this library can contribute real evidence. Never paste their payload into chat.

Offline checks (no Owner input):

```powershell
py -3.10 -m unittest tools.tests.test_ios_certificate_pair tools.tests.test_ios_release_pipeline tools.tests.test_ios_candidate_inspector -v
```

## Short Owner return sequence and remaining software gaps

1. **Local creation completed (Owner report):** Owner refreshed exact approval
   to `f8c21fef3dc964b3df19121dc72d23d7f76a1f3b` and reported confirmed success.
   Do not rerun creation, replace the key or treat this as independent inspection.
2. **Apple issuance:** after creation succeeds, Owner checks the intended team
   and certificate type and submits only `distribution.csr` to Apple in an
   explicitly scoped issuance step. Never upload `distribution-private-key.pem`
   or the API `.p8` as the CSR. Owner now reports Apple Distribution issuance
   and certificate download complete; the actual file remains uninspected.
3. **Validation/conversion completed (Owner report):** after exact approval at
   `c458d29326072444987fff70b43aa3ec46a5bfa1`, TASK-186 returned
   `OFFLINE_PACKAGE_VERIFIED` / `confirmed_success`. Do not package again.
   Offline chain/purpose/private-key matching do not establish Team/profile,
   revocation, native macOS import or signing authority.
4. **Profile/cloud custody:** Owner reports App Store Connect profile downloaded;
   no profile contents were inspected here. Verify the existing profile rather
   than generating replacements. Protected Environment custody and a reviewed
   temporary-keychain workflow remain unimplemented. No public
   Actions artifact is an approved place for private signing assets or an IPA.
5. **Build then upload separately:** exact candidate signing/cleanup/inspection,
   private artifact handoff and one upload remain separate gates. Existing
   lifecycle tests are simulated, not a live adapter. Verify provider/staging,
   privacy/deletion and actual device behavior before any tester/public release.

Owner need not perform steps2–5 merely to finish step1. Their acceptance and
private-input boundaries must be ready before requesting another Owner session.
No stage grants the next stage automatic authority; no repeated generation or
upload after an uncertain result.

## TASK-186 local packaging boundary

The separate packaging operator is implemented and tested with fictional assets.
Owner subsequently reports the exact approved operation succeeded (see above).
The instructions below describe its contract, not a request to execute again.
Do not execute against genuine assets until independent review, hosted checks
and exact Owner approval of the reviewed commit. Do not paste private inputs.
It will preserve the existing CSR/key and exclusively create an encrypted
`distribution.p12` in the existing protected local directory; no plaintext key
file, public artifact, network call, system keychain or Apple resource mutation.
Owner will later place the downloaded certificate as `distribution.cer` in that
directory; do not search Downloads or copy it automatically during development.

Pinned public Apple Root and WWDR G3 are repository trust inputs, not private
Owner assets. Offline chain signatures/validity and Apple Distribution purpose
do not establish current revocation status, intended Team/App/profile or signing
authority. Those remain separate gates. Unknown chains or critical extensions
must stop rather than fetching AIA URLs or trusting caller/system anchors.

The fixed distribution profile is based on Apple WWDR CPS1.32 section4.11.24:
RSA/SHA2, digital-signature usage, code-signing EKU, non-CA and both submission
markers. This does not rely on a displayed certificate name. Only the pinned
legacy root self-signature may use SHA1; leaf signatures may not.

PKCS12 password encryption alone is not a safe custody boundary. Keep the
restricted local ACL and separate strong password; do not email/upload the file
or put it in Git. Future secure cloud custody requires its own approved flow.
Modern AES256/SHA256 packaging compatibility with the eventual macOS import must
be demonstrated there, not inferred from a Python roundtrip.

Reviewed entry will be `py -3.10 -m tools.ios_certificate_packaging
--expected-commit <reviewed-full-SHA>`. Default preflight only opens/validates
metadata-bound handles and checks repository/trust configuration; it does not
read file payloads, prompt for passwords or create output. A separately released
Owner run adds `--execute`, displays the exact local action, then requires hidden
`PACKAGE P12 <reviewed-full-SHA>` confirmation. Existing key password, new P12
password and its repeat are entered only in that interactive local terminal.
No shell arguments/environment/input-file fallback is supported for secrets.

The operator locks directory rename and input write/delete while using the same
native handles for metadata, ACL and I/O. It rejects unsafe ACL, reparse paths,
multiple hardlinks, oversized input and existing output. It never repairs ACLs.
New output is created with an explicit current-user owner and protected
single-user DACL, not the process token's potentially different default owner.
The returned handle is checked before any payload write. Existing input owner
checks remain strict; an elevated terminal does not authorize taking ownership
or changing original files. Use a normal personal terminal for the Owner flow.
Copy (do not move) the public downloaded certificate into the protected folder
only when the exact Owner procedure is released; moving may retain unsafe ACLs.
Keep the original download; do not copy any private key into Downloads or Git.

`preflight_passed` proves metadata only. `confirmed_success` proves local offline
package checks, not signing permission. `pre_execution_rejected` requires fixing
the reported fixed stage/reason and a new preflight; `uncertain` preserves partial
encrypted output and prohibits retry/deletion until a separate reconciliation.
No sensitive values, raw exceptions, private hashes or file contents appear in
the single sanitized result. Same-user malware, administrators, device loss and
guaranteed Python memory zeroization remain outside these safeguards.

Sources: [Apple PKI](https://www.apple.com/certificateauthority/),
[WWDR purposes](https://developer.apple.com/help/account/certificates/wwdr-intermediate-certificates/),
[Apple WWDR CPS1.32](https://images.apple.com/certificateauthority/pdf/Apple_WWDR_CPS_v1.32.pdf),
[cryptography50 PKCS12](https://cryptography.io/en/50.0.0/hazmat/primitives/asymmetric/serialization/).

Native ownership reference:
[Microsoft: owner of a new object](https://learn.microsoft.com/en-us/windows/win32/secauthz/owner-of-a-new-object).

Parsing/validity API reference:
[cryptography X.509](https://cryptography.io/en/50.0.0/x509/reference/).

## TASK-187 profile content boundary

The pure in-memory `tools.ios_profile_validation` core checks bounded decoded
XML plist content against expected App/Team/certificate categories and an explicit
verification time. It is not a `.mobileprovision` reader, CMS decoder, Owner-input
wrapper or cloud signing entry. Only fictional fixtures are used in this delivery.
Binary plist is deliberately unsupported; XML entity expansion and arbitrary DTD
declarations are rejected. A recognized standard Apple DTD is never fetched.

Success is `PROFILE_CONTENT_MATCH_ONLY`. Even a forged profile with matching
content cannot establish CMS signature, Apple trust, revocation, private-key
possession, native import, signing, upload or release authority. No caller flag
can upgrade this result. The initial contract is intentionally narrower than all
historical Apple profiles; unsupported prefixes/types stop, not auto-correct.

The existing IPA inspector's `security cms -D` call is not accepted as proof of
trusted CMS verification or a side-effect-free standalone intake. Apple's source
contains certificate import paths and does not propagate every signer verification
failure as a decode failure. Its existing output must not be promoted into a new
profile trust gate. TASK-187 does not invoke or alter that native path.

Before real signing, separately reviewed maintained native CMS verification must
establish the signer, Apple trust/purpose and exact authenticated content. Then
the content core can contribute correspondence evidence. Native macOS import of
the actual PKCS12 encryption format is another independent prerequisite; Python
roundtrip and simulated lifecycle traces cannot replace it. No cloud workflow or
real downloaded-profile inspection is released by this content-only delivery.

Sources: [Apple profile structure](https://developer.apple.com/documentation/technotes/tn3125-inside-code-signing-provisioning-profiles),
[Apple CMS command implementation](https://github.com/apple-oss-distributions/Security/blob/main/SecurityTool/macOS/cmsutil.c).

## Official references checked 2026-09-08

- [GitHub runner scope/cost](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [macOS signing setup](https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications)
- [Apple API key permissions](https://developer.apple.com/help/app-store-connect/get-started/app-store-connect-api)
- [Apple upload and processing](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/)
