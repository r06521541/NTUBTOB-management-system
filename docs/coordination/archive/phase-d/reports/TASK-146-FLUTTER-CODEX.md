# TASK-146 Flutter Writer Report

## Delivery

- Composed the notification centre into the authenticated Flutter home only
  for server-derived `notifications:read` capability holders.
- Reuses the principal-scoped notification cache and existing terminal/session
  purge boundaries; offline opens remain read-only.
- Added controller single-flight guards for loading and read mutations, so the
  badge and centre update only after a successful server mutation.
- Extended the fictional production-shaped demo with deterministic read and
  unread notification data using the production notification widgets.

## Verification

Executed with the repository's Flutter 3.47.0 / Dart 3.13.0 wrapper:

```text
flutter test test/notification_center_test.dart test/basic_app_test.dart test/production_demo_test.dart
88 tests passed

flutter analyze lib/basic_app.dart lib/notification_center.dart lib/production_demo.dart test/basic_app_test.dart test/notification_center_test.dart test/production_demo_test.dart
No issues found

dart format --output=none --set-exit-if-changed <owned Dart files>
No formatting changes required
```

`git diff --check` passed. No emulator, staging, backend, provider, database,
deployment, Secret/IAM, signing, or store operation was performed.

## Handoff

Writer self-review complete. Main Work should review the capability gate,
terminal/session and Person lifecycle, notification request single-flight, and
home badge/read-state integration before the hosted Flutter gate.

## Correction round

- Added epoch-based controller invalidation so pending loads or mutations cannot
  restore stale notification memory/cache state after lifecycle invalidation.
- Terminal notification session failures now invalidate the controller and
  report to the root Basic lifecycle for canonical session-expired rendering.
- Offline cache absence/corruption now renders explicit non-authoritative
  evidence-unavailable state instead of an authoritative-looking empty list.
- Correction verification: `flutter test test/notification_center_test.dart
  test/basic_app_test.dart` (82 passed), affected `flutter analyze`, and
  affected Dart formatter check all passed.
- Final narrow completion serializes cache writes and invalidation purges, and
  invalidates root-held controller state on logout, terminal expiry, Person
  change, and capability loss.
- `forbidden` now clears notification authorization state without converting a
  still-valid Basic session into a terminal session.
