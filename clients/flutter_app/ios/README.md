# iOS distribution contract

This directory contains a repository-only guard for future TestFlight and App
Store candidates. It does not prove that an archive was built, signed, uploaded,
reviewed, installed, or exercised on a real device.

## Build modes

The Xcode `Validate Auth Config` build phase runs both
`validate_store_release_config.sh` and the existing Google callback validator.
The store validator accepts only these combinations:

| App flavor | Client mode | Xcode configuration | Distribution channel | Current result |
| --- | --- | --- | --- | --- |
| `development` | `fake` | `Debug`／`Profile` | absent | allowed without signing/provider values |
| `staging` | `real` | `Debug`／`Profile` | absent | non-distribution development only; cannot claim TestFlight/signing readiness |
| `staging` | `real` | `Release` | `testflight` | allowed only with externally supplied signing metadata |
| `production` | `real` | `Release` | `app-store` | blocked until Sign in with Apple is implemented and reviewed |

Any missing, mixed, unresolved, or unknown combination exits with status 2.
Non-distribution Debug／Profile preserves existing fake and staging development
paths but rejects any TestFlight channel or release-signing claim. Release
candidates also require explicit numeric version
and build values, a non-debug bundle identity, code signing enabled, and
non-empty team/profile/expanded signing identity values supplied by Xcode.
The validator never prints those values.

The validator scans every `DART_DEFINES` entry before selecting a mode. Empty,
malformed, non-canonical, binary/multiline, or non-`key=value` entries fail;
release-critical environment, service-auth, and Apple keys must occur exactly
once when required. Development fake mode rejects service definitions, while
real mode requires the API, LINE, and two Google definitions. Other
syntactically valid Flutter/system definitions may coexist and do not affect
the release decision.

## Private build configuration

`Flutter/StoreReleaseConfig.xcconfig.example` is a key-name template. Copy it
to the gitignored `Flutter/StoreReleaseConfig.xcconfig` only on an
Owner-approved macOS/Xcode builder, and inject real signing/provider metadata
there or through the approved build environment. Do not commit that private
file, an entitlement bound to a real App ID, certificates, profiles, account
metadata, provider identifiers, or passwords.

`Flutter/StoreReleaseContract.xcconfig` is deliberately repository-owned and
included after the optional private file. Its current
`APPLE_SIGN_IN_REPOSITORY_STATUS=not_implemented` marker cannot be overridden
by private configuration. The validator also reads this committed file and
requires the resolved Xcode values to match it, so a command-line build setting
cannot bypass the repository state. A production/App Store build therefore
fails closed.

## Apple public-release gap

`Runner/Runner.entitlements.example` documents the expected entitlement shape
but is not bound to the target. A future separately reviewed auth delivery must
complete all of the following before changing the repository marker to
`ready`:

1. Implement Apple login, backend token verification, identity linking,
   recovery/conflict behavior, session/logout handling, and offline/error UX.
2. Add direct client/server tests and verify the Apple button/flow on supported
   real iOS devices; a compile-time marker alone is not evidence.
3. Enable the capability in the approved Apple provider/App ID, bind a reviewed
   `Runner/Runner.entitlements`, and supply provider/signing state externally.
4. Pass the public iOS gates in
   `docs/releases/MOBILE_RELEASE_MATRIX.md`, including privacy, deletion,
   metadata, production-backend, push/deep-link, and anonymous-crash evidence.

Only after that review may a production build supply
`APPLE_SIGN_IN_RUNTIME_IMPLEMENTED=true` in `DART_DEFINES`. The repository
validator is one precondition, not App Store, Xcode, signing, or runtime proof.

For a production vector on macOS, entitlement validation uses the fixed
`/usr/bin/plutil` path to require the Apple key to be an array whose extracted
value is exactly `Default`; a `Default` string under another key is rejected.
The deterministic non-Darwin shell regression uses a strict portable
key-to-array association parser, but that fallback is not macOS or codesign
evidence. The future Apple delivery must additionally inspect the entitlement
embedded in the signed archive; validating the source plist alone cannot prove
what was codesigned.

## Local deterministic check

On a POSIX shell, run:

```sh
/bin/sh ios/tests/validate_store_release_config_test.sh
```

The test uses fictional metadata only. Windows verification may run the same
script with Git Bash. macOS/Xcode archive, codesign inspection, TestFlight
installation, provider configuration, App Store Connect work, and real-device
evidence remain future Owner-gated operations.
