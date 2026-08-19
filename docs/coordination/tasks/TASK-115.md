# TASK-115: Flutter staging emulator acceptance

task_type: delivery
delivery_group: mobile-staging-activation
requires_independent_pr: true
status: ready_for_pr
base_commit: 30b66cd79da0f2442ae3e9f1c2a7e091e82069be

## Goal

Validate the Flutter client against the isolated fictional mobile staging
environment on an Android emulator, and close defects exposed by native LINE
login and attendance reply recovery without expanding production scope.

## Delivered behavior

- Serialize the native LINE login lifecycle so a timed-out attempt cannot start
  a second provider flow or retain exchange authority.
- Apply the server-authoritative attendance `ownReply` after a successful
  mutation/readback instead of leaving the locally selected value on screen.
- Exercise native LINE callback, authenticated Basic isolation, game detail and
  five-state attendance, uncertain same-intent recovery, authoritative restore,
  offline read-only cache, online recovery and final logout/cache purge.

## Boundaries

- Android emulator and dedicated fictional staging only; no production,
  release signing/store upload, true notification or sensitive-value capture.
- Credentials, QR and provider consent remain Owner actions. Reversible,
  low-sensitive fictional staging diagnostics follow DEC-098 agent autonomy.
- iOS runtime/signing and physical-device Android acceptance remain deferred.

## Verification

- Flutter analyze, focused widget tests and full Flutter tests.
- Hosted Flutter format/analyze/test/debug-build final gate.
- Privacy-safe emulator evidence for session, capability, offline and logout
  behavior; no raw token, provider subject or response body collection.

