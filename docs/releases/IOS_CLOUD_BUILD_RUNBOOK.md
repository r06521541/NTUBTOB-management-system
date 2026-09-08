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
Windows-to-Apple certificate bootstrap still needs reviewed implementation and
is not provided by this rehearsal.

## Windows local CSR preparation (TASK-184)

The certificate-preparation operator is a separate local-only boundary, not the
cloud rehearsal or upload adapter. Owner reports the upload API `.p8` is safely
saved and Apple Certificates is empty; neither report authorizes reading that
file, replacing a key or creating an Apple certificate automatically.

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

## Official references checked 2026-09-08

- [GitHub runner scope/cost](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [macOS signing setup](https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications)
- [Apple API key permissions](https://developer.apple.com/help/app-store-connect/get-started/app-store-connect-api)
- [Apple upload and processing](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/)
