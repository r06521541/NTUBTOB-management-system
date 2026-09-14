# Native iOS signing baseline (no upload)

TASK-198 / DEC-110 is the current route. The old local-controller workflow is
hard-disabled; its source and original journals remain intact. Do not execute
the old operator, create a successor, clear its journal, or regenerate keys.

## What this delivery proves

The manually triggered `ios-native-signing.yml` uses the existing Flutter 3.47.0,
Xcode 26.3 (17C529), standard GitHub-hosted `macos-15`, native `security`, Xcode
archive/export and the existing artifact-only IPA inspector. No custom CMS
envelope parser, Swift credential transport or Windows controller participates.
There is NO Apple upload/API key, automatic provisioning, tester mutation or
public release step. A verified baseline is not TestFlight availability.

The first live baseline is deliberately signing-only. Once the native route is
proved, add an independently reviewed official Apple upload step on the same
runner, with separate ASC key custody and read-only processing reconciliation.
This will require another build (the baseline IPA is deleted), not retyping or
re-importing the persistent signing Secrets. Do not publish an IPA as a public
Actions artifact to avoid that build. Do not reuse a build already uploaded.

## One-time setup checklist — not a command to execute yet

After accepted source and successful required CI, Owner configures repository
Settings → Environments → **ios-native-signing**. Do not click Run workflow first:
GitHub can automatically create a missing, unprotected Environment.

- Required reviewer: Owner; no administrator bypass; deployment branch only
  `main`. Keep self-review available when Owner is the only reviewer.
- No signing materials in repository/organization Secrets, workflow inputs,
  ordinary Variables, chat, clipboard, source or artifacts.
- Keep the existing `ios-owner-testflight` Environment and old operation evidence
  unchanged. No new certificate/key/profile is required by this source delivery.

Environment Secrets (three separate values, saved once):

| Secret name | Existing material |
| --- | --- |
| `IOS_DISTRIBUTION_P12_BASE64` | Base64 of the existing `distribution.p12`, not the CSR or `.cer` alone |
| `IOS_DISTRIBUTION_P12_PASSWORD` | Password chosen for that P12, not Apple account password |
| `IOS_DISTRIBUTION_PROFILE_BASE64` | Base64 of the existing App Store Connect `.mobileprovision` |

No `.p8` is used in this baseline. Neither the ASC upload key nor the Sign in
with Apple key belongs in these three fields. Base64 is encoding, not encryption.
Do not use an online converter. Before Owner provides payloads, Main must hand
off the reviewed, exact private-input setup action; this document intentionally
does not introduce an ad-hoc shell/clipboard secret converter. Environment rule
setup can be completed without touching any payload.

Environment Variables (non-secret metadata; Main should reuse prior approved
metadata where available, and verify bindings rather than make Owner retype it):

| Variable | Meaning |
| --- | --- |
| `IOS_TEAM_ID` | Existing Apple Team, ten uppercase letters/digits |
| `IOS_API_BASE_URL` | Exact `mobile-api-staging` URL in `ntubtob-mobile-staging` |
| `IOS_LINE_CHANNEL_ID` | Existing staging LINE Login channel, numeric |
| `IOS_GOOGLE_CLIENT_ID` | Existing Google **iOS** client for this bundle |
| `IOS_GOOGLE_SERVER_CLIENT_ID` | Existing Google Web/server client, distinct from iOS |

The code's staging service-name check is not proof of GCP project ownership.
Before live dispatch, Main must independently verify the exact configured URL,
provider/App/Team binding, Environment protections, old run terminal/transfer
absence, no active competing execution, reviewed main SHA and cost budget.
This is an approved new path, not a replay or second old-controller successor.
Standard public-repository hosted compute has no extra runner charge under the
currently documented GitHub terms; verify that remains true. No larger runner,
artifact storage, new service or plan upgrade. IOS-TF-01 aggregate USD20 cap stays.

## Each execution

1. Main records the reviewed full main SHA and baseline version/build in TASK-198.
   Version/build are public metadata; they do not prove the number is free in ASC.
2. Owner manually triggers **iOS native signing baseline (no upload)** on main and
   approves use of the configured Environment. No local password prompt or
   continuously running Windows terminal. Never use GitHub Re-run jobs blindly.
3. Nonsecret checks and dependency setup run before the step receives Secrets.
4. The native step reports `stage=... STARTED`, then a sanitized result. Stages
   include P12 import, profile decode/binding, identity selection, archive, export,
   signature/profile inspection, search restore, Keychain deletion and cleanup.
5. Only `SIGNED_BASELINE_VERIFIED` plus successful final absence audit proves this
   signed baseline. It always reports upload/device/public release false.

## Custody and failure handling

GitHub persists encrypted Secrets; an approved runner receives plaintext. The
adapter permits necessary `security` password arguments and 0600 temporary
files/0700 dedicated Keychain directory. It removes secret environment fields
before native/build commands and passes no secret arguments through a shell.
It never echoes command arguments or raw native output. Masking is not a guarantee
and same-user compromised code can inspect argv/files/memory. Reviewed build
scripts execute during signing; this is not a key-isolated execution model.

Import uses named `codesign` access, not `-A`; native Apple partition authorization
is not a single-executable sandbox. Original search order is restored and default
Keychain identity is checked. `security cms -D -k <dedicated-keychain>` decodes
the existing controlled profile; this is not a custom CMS trust proof or a claim
of no Keychain side effects. Xcode and signed artifact checks remain distinct from
Apple server validation/processing.

The job deletes its P12 file, two exact installed profile files, three generated
configuration/entitlement files, dedicated Keychain, archive/IPA and private build
output. It never deletes a user directory, old journal or original asset. Persistent
GitHub Secrets intentionally remain until explicit rotation/removal, not after
each build. There is no raw log/IPA/cache upload. Normal cleanup is in `finally`;
forced VM termination is only a disposal backstop, not proof cleanup ran.

Failure preserves `failure.stage/reason/exit_code` and independent
`cleanup_failures`. Native output is privately captured; only reviewed fixed
patterns become public reason codes. Unknown output keeps stage/exit status and
`CLI_FAILED`; its raw text is not retained. This is an explicit diagnostic limit,
not proof the password is wrong. Read-only/source investigation comes next, not
another request to enter the password. Timeout/unreaped process or residual files
cannot become success. No automatic retries, raw dump mode or reset mechanism.

## Verification

`py -3.10 -B -m unittest tools.tests.test_ios_native_signing
tools.tests.test_ios_candidate_inspector -v` runs fictional command-shaped
responses through the real adapter and inspector. The single native smoke runs
only on ephemeral GitHub macOS: create/configure Keychain, deliberately invalid
fictional P12 import, restore/delete. Neither fake tests nor this negative smoke
proves real certificate import, successful signing, upload or phone behavior.

Sources: [GitHub native signing](https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications),
[Apple security command implementation](https://github.com/apple-oss-distributions/Security/blob/main/SecurityTool/macOS/security.c),
[Flutter iOS release](https://docs.flutter.dev/deployment/ios).
