# Native iOS signing baseline (no upload)

TASK-198 / DEC-110 / DEC-111 is the current route. The old local-controller workflow is
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

## One-time setup checklist

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
Do not use an online converter. Use the reviewed one-field setup below after
source acceptance/CI; Main never runs its private-input mode. Environment rule
setup can be completed without touching any payload.

### Owner-only one-field setup

`tools.ios_native_secret_setup` is a small adapter for official `gh secret set`,
not a signing controller. It never copies, repairs or deletes local originals,
creates a journal, or dispatches a workflow. Requires Windows, existing GitHub CLI
2.97.0 at its standard Program Files location, Python3.10, existing reviewed
custody dependencies and the Owner's existing GitHub CLI login (not a new token).

Main supplies the full reviewed merged SHA as `REVIEWED_MAIN_SHA` in the following
commands; it is public source metadata, not a password. Run from the clean main
checkout. Do NOT paste the literal placeholder. First run without `--execute`
to verify source, Owner login, Environment protections and selected-field presence.

```powershell
py -3.10 -B -m tools.ios_native_secret_setup p12 --expected-commit REVIEWED_MAIN_SHA
```

Then use the SAME reviewed SHA, only after `READY`, one command at a time:

```powershell
py -3.10 -B -m tools.ios_native_secret_setup p12 --expected-commit REVIEWED_MAIN_SHA --execute
py -3.10 -B -m tools.ios_native_secret_setup profile --expected-commit REVIEWED_MAIN_SHA --execute
py -3.10 -B -m tools.ios_native_secret_setup password --expected-commit REVIEWED_MAIN_SHA --execute
```

The tool prints exact repo/Environment/field/count, then asks for the displayed
`SET p12`, `SET profile` or `SET password` confirmation. Private input is hidden
with length-only feedback. File prompts accept existing absolute paths using
either slash direction, without quotes. Use the already protected local
`distribution.p12` and `.mobileprovision`, not CSR/CER/P8. Existing handle-bound
custody checks remain private: no inherited-source ACL exception or auto-repair.
An ACL/path rejection is not a password error; send only the sanitized result to Main.
The password prompt preserves spaces/UTF-8 and rejects control characters; it is
the P12 password, not the Apple account password. It is never Base64-encoded.

Files are Base64-encoded in memory, at most36KiB raw/48KiB encoded. No clipboard,
Base64 output, temp file, dotenv, body argument, inherited secret env, raw CLI log
or traceback. Only a private stdin pipe supplies the selected value to fixed-host
official gh, which encrypts it before sending. Source/identity/policy/absence are
checked again after input. Stored inputs stay in GitHub; no need to retype them
for subsequent builds. Python/gh cannot guarantee memory zeroization.

Run setup in ONE Owner window, with no concurrent manual Secret edits, agents or
signing run. GitHub provides create-or-update, not atomic create-if-absent. The
absence recheck narrows but does not eliminate the race; no absolute atomic
no-overwrite claim is made. Observed existing fields are never deliberately set.

- `READY`: no private input/write; Owner can execute this selected field once.
- `STORED_METADATA_CONFIRMED`: CLI exit0 plus name presence; proceed to next field.
  This does not verify the stored value, certificate validity or signing.
- `ALREADY_PRESENT`: no input/write; preserve it. Presence alone is not value proof.
- `STOP`: inspect `failure.stage/reason/exit_code`, separate `cleanup_failure` and
  `write_state`. Correct only a selected input rejected before any write. For an
  attempted/unknown write, cleanup failure, or postcheck failure, STOP ALL setup
  and ask Main for read-only review; do not run the next field, repeat the command,
  overwrite/delete a Secret or treat a later absent name as proof of zero mutation.

One invocation submits at most one Secret set, without automatic retries. There
is no new local attempt journal, so this stop rule requires the Owner's observed
result; do not claim a software-enforced cross-invocation retry budget. If the
window closes without a final result, that is uncertain and also requires review.
Only sanitized final JSON is evidence; raw native diagnostics are discarded after
fixed classification. A known CLI success survives a subsequent verification or
cleanup failure. Setting Secrets is not authorization to start the signing job.

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

The first real run34880271702 on main a4974b6967c65cecbf0b45063f8a809549c8d07e
completed native signing, inspection and cleanup; exact sanitized receipt/audit
verified, artifacts0. It did not upload. Do not rerun that successful baseline.

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

### ASC preparation (no upload action yet)

DEC-111 permits one additional Environment Secret, `IOS_ASC_UPLOAD_CREDENTIAL`.
It contains a compact JSON package of ASC Key ID, Issuer ID and Base64 existing
p8 bytes. It excludes local path, Owner email, signing materials and the separate
Sign in with Apple key. Its API powers remain those of the existing ASC key;
encrypted storage and step-level injection are not same-runner isolation.

After source acceptance/CI, Main supplies the exact reviewed merged SHA. On the
clean main checkout, Owner uses `tools.ios_native_secret_setup asc` with the same
`--expected-commit` convention above: first without `--execute`, then once with it
only after READY. The sole hidden prompt is `SET asc`; no password, key path,
Key ID or Issuer re-entry. Already-present and dry-run paths do not read any
private file. Never run an execute command supplied with a literal placeholder.

The setup holds the existing protected `testflight-inputs.json` and its selected
ASC p8 through one Reader/verify/close sequence. No scan, copy, rewrite, ACL repair
or Login-key read. One official gh stdin write follows a fresh source/identity/
protection/presence check. A local P256/PKCS8 check does not prove Apple accepts
the key/IDs, role or App access; no live Apple API is called by setup. A primary
input failure and a secondary close failure survive together. The STOP/no-retry
rules above apply unchanged, including serialization by Owner.

`python -m tools.ios_native_upload probe` in the existing secret-free macOS CI job
checks exact Xcode26.3/17C529, resolves altool with xcrun, then invokes only --help.
It reports fixed option-presence booleans, not credentials, an IPA, or guessed
Apple response fields. Unknown help is evidence to inspect, not upload readiness.
The module currently has NO upload action; actual argv and cleanup require a
later reviewed native upload slice based on this platform evidence.

`tools.ios_native_receipt` is a GET-only signing-success reader. Supply public
`--run-id`, `--job-id`, `--expected-commit`; it binds the completed successful
main/first-attempt native run and job, checks artifacts0, then accepts exactly one
typed signing-success record and one absence audit. It is not an arbitrary log
viewer or a failed-run/Apple upload parser. Failed/missing/contradictory evidence
stops without printing rejected content; underlying CLI failures retain stage,
safe reason, exit code and secondary cleanup failure.

GitHub CLI2.97 refuses terminal escape sequences in non-JSON responses even with
piped stdout. The reader's documented `--allow-escape-sequences` is scoped ONLY
to captured memory pipes, never a terminal/raw file/log dump. Parsing is bounded
to1MiB and each JSON record4KiB; the existing CLI helper checks its1MiB output
limit after capture (not a streaming memory ceiling). Unknown or malformed
records cannot become a signed receipt. This fixes receipt visibility, not signing
or upload; no password entry or baseline rerun is a remedy for this CLI guard.

Direct offline suite:
`py -3.10 -B -m unittest tools.tests.test_ios_native_secret_setup
tools.tests.test_ios_native_upload tools.tests.test_ios_native_receipt -q`.

`py -3.10 -B -m unittest tools.tests.test_ios_native_signing
tools.tests.test_ios_candidate_inspector -v` runs fictional command-shaped
responses through the real adapter and inspector. The single native smoke runs
only on ephemeral GitHub macOS: create/configure Keychain, deliberately invalid
fictional P12 import, restore/delete. Neither fake tests nor this negative smoke
proves real certificate import, successful signing, upload or phone behavior.

Sources: [GitHub native signing](https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications),
[Apple security command implementation](https://github.com/apple-oss-distributions/Security/blob/main/SecurityTool/macOS/security.c),
[Flutter iOS release](https://docs.flutter.dev/deployment/ios),
[official gh Secret setup](https://cli.github.com/manual/gh_secret_set),
[pinned CLI stdin behavior](https://github.com/cli/cli/blob/v2.97.0/pkg/cmd/secret/set/set.go).
Native upload reference: [Apple upload builds](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/).
Receipt guard: [GitHub CLI2.97 API implementation](https://github.com/cli/cli/blob/v2.97.0/pkg/cmd/api/api.go).
