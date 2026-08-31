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
| `production` | `real` | `Release` | `app-store` | blocked pending Apple provider/signing/runtime and public release gates |

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

## Apple repository implementation and public-release gap

`Runner/Runner.entitlements.example` documents the expected entitlement shape
but is not bound to the target. The real iOS Flutter composition now includes a
dependency-free `AuthenticationServices` bridge. It hashes the one-time raw
nonce with lowercase SHA-256 for the native request and returns only the Apple
identity token plus its single-use authorization code; Flutter sends that exact
credential envelope and the same raw nonce to the Mobile API. No email, relay
email, name, Apple user identifier, or profile hint is returned or used for
identity linking. The server-verified
stable Apple subject remains the sole provider identity key.

The repository implements local ID-token verification followed by one-shot
authorization-code exchange, encrypted refresh-credential retention, signed
server-notification validation, idempotent receipts, and local identity/session/
credential revocation. Active provider-token revocation, credential-state
checks, provider/App ID and notification URL configuration, signing, deployment,
and real-device Apple login remain public provider/runtime Owner gates.

Repository implementation does not make the public release ready. A separately
reviewed delivery must complete all of the following before changing the
repository marker to `ready`:

1. Independently accept the repository login, backend verification, identity
   linking, recovery/conflict, session/logout, offline/error, and direct-test
   evidence.
2. Compile and test the bridge with the pinned Flutter toolchain on macOS/Xcode,
   then verify the Apple button/flow on supported real iOS devices; source and
   compile-time markers alone are not runtime evidence.
3. Enable the capability in the approved Apple provider/App ID, bind a reviewed
   `Runner/Runner.entitlements`, and supply provider/signing state externally.
4. Independently accept the repository authorization-code/refresh-token and
   server-notification lifecycle, then complete provider credential-state and
   active token-revocation evidence without exposing provider material.
5. Pass the public iOS gates in
   `docs/releases/MOBILE_RELEASE_MATRIX.md`, including privacy, deletion,
   metadata, production-backend, push/deep-link, and anonymous-crash evidence.

Only after that review may a production build supply
`APPLE_SIGN_IN_RUNTIME_IMPLEMENTED=true` in `DART_DEFINES`. The repository
validator is one precondition, not App Store, Xcode, signing, or runtime proof.

For a production vector on macOS, entitlement validation uses the fixed
`/usr/libexec/PlistBuddy` path and exact colon paths. It requires the Apple key
container to be an array, element 0 to equal `Default`, and element 1 to be
absent; a `Default` string under another key or a second array value is rejected.
The deterministic non-Darwin shell regression uses a strict portable
key-to-array association parser, but that fallback is not macOS or codesign
evidence. The future Apple delivery must additionally inspect the entitlement
embedded in the signed archive; validating the source plist alone cannot prove
what was codesigned.

The non-Darwin test locks the fixed PlistBuddy path and both array-element
commands as a source contract. It does not execute PlistBuddy or claim macOS
evidence; the Darwin branch still requires a future macOS runner check.

## Local deterministic check

On a POSIX shell, run:

```sh
/bin/sh ios/tests/validate_store_release_config_test.sh
```

The test uses fictional metadata only. Windows verification may run the same
script with Git Bash. macOS/Xcode archive, codesign inspection, TestFlight
installation, provider configuration, App Store Connect work, and real-device
evidence remain future Owner-gated operations.
