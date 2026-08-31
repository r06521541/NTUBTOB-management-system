# TASK-171 Flutter／iOS writer report

## Delivered repository behavior

- Added a dependency-free iOS `AuthenticationServices` bridge registered with
  Flutter's implicit engine. It accepts one bounded raw nonce, places only the
  lowercase SHA-256 digest on the Apple request, requests no profile scopes, and
  returns only a bounded identity token.
- Added iOS-only Flutter Apple login and exchange behavior. The Mobile API body
  is exactly `id_token`, the same raw `nonce`, `login_attempt_id`,
  `installation_id`, and `platform`; no email, name, Apple user identifier,
  authorization code, or profile hint is transmitted.
- Reused the existing pending-review, session acceptance, explicit identity-link
  candidate/proof, conflict, timeout lock, and cancellation/error UX. Apple is
  hidden from fake and unsupported compositions; offline/unsupported attempts
  perform zero native and API calls.
- Added deterministic Dart and Swift nonce-hash evidence plus source-contract
  checks for the Xcode project registration and fail-closed release marker.

The stable Apple subject remains a server-verified sole identity key. This
client does not inspect or persist it and never performs profile-based automatic
merging.

## Verification

- `dart format --output=none --set-exit-if-changed` on the four changed Dart
  files: passed.
- `flutter test test/apple_auth_test.dart`: 10 passed.
- `flutter test test/apple_auth_test.dart test/identity_link_test.dart test/integration_test.dart test/basic_app_test.dart`:
  189 passed.
- `flutter analyze`: no issues.
- `ios/tests/validate_store_release_config_test.sh`: all contract cases passed
  under Git Bash.
- `git diff --check`: passed.

All test identities, tokens, nonces, identifiers, and session values are
fictional. No Apple/Google/LINE account, provider identifier, key, signing
material, Secret, cloud, deployment, production service, or real user/device
was accessed or changed.

## Remaining fail-closed gates

`Flutter/StoreReleaseContract.xcconfig` deliberately remains
`APPLE_SIGN_IN_REPOSITORY_STATUS=not_implemented`. Independent review and
acceptance, macOS/Xcode compilation, capability/App ID and entitlement/profile
binding, provider/signing configuration, signed archive inspection, real-device
smoke, and TestFlight/App Store evidence remain external Owner-gated work. This
report does not claim Xcode, provider, signing, archive, or public-release
readiness.

This slice intentionally returns only a nonce-bound identity token. It does not
return an authorization code; server-side authorization-code validation and
Apple refresh-token acquisition are therefore not implemented. Apple
credential-state checks, Apple server-to-server notifications, and the account
revocation lifecycle are also unimplemented public provider/runtime Owner gates.
