# TASK-146: Flutter notification centre composition

- Task type: delivery
- Delivery group: `mobile-notification-centre-composition`
- Risk level: L2 state／capability／cache／offline
- Repository authority: `1bb2417cac7b18d58bf4a453ad4bdb8607ef1894`
- Owner gate: none for repository work; deployment, staging, Secret/IAM,
  real provider/data, signing and stores remain excluded

## Goal

Make the durable notification foundation delivered by TASK-145 reachable from
the real signed-in Flutter experience. A member with `notifications:read` can
see an unread badge, open the notification centre, read cached content offline,
and update read state online with truthful lifecycle behaviour.

## Writer claim

- claim_id: `task-146-flutter-notification-centre-writer`
- lease_version: 1
- actor_id: `01a028ae-041c-7313-b917-417a0932e12d`
- role: `codex-writer`
- write: true, limited to the owned paths
- report_to: `main-work`
- implementation branch: `codex/task-146-notification-center-writer`
- owned paths:
  - `clients/flutter_app/lib/basic_app.dart`
  - `clients/flutter_app/lib/notification_center.dart`
  - `clients/flutter_app/lib/production_demo.dart`
  - `clients/flutter_app/test/basic_app_test.dart`
  - `clients/flutter_app/test/notification_center_test.dart`
  - `clients/flutter_app/test/production_demo_test.dart`
  - `docs/coordination/reports/TASK-146-FLUTTER-CODEX.md`

## Scope

- Add a notification-centre entry and unread badge to the authenticated home
  experience only when the server-derived Person has `notifications:read`.
- Compose the existing `NotificationApi`, principal-scoped `NotificationCache`
  and `NotificationCenterController` through `BasicBootstrapApp` and the real
  navigation path.
- Load once per explicit open/refresh operation; rapid taps or rebuilds must not
  create duplicate concurrent requests.
- Keep the home unread badge consistent after single and mark-all-read actions.
- In offline mode, use only the last successful principal-scoped cache, show
  truthful last-sync/read-only state and issue no read mutation.
- Purge/fail closed on terminal session, logout, Person change, authorization
  loss or cache corruption, reusing the TASK-145 lifecycle boundaries.
- Extend the production-shaped fake demo with deterministic empty, unread,
  read and offline notification-centre states using production widgets.

## Invariants and non-goals

- Capability absence hides the entry and must not trigger notification API
  requests. Flutter does not infer authorization from a role label.
- No backend, OpenAPI, model, schema, migration or notification-retention change.
- No FCM/APNs, LINE, Discord, real provider, device registration, OS push deep
  link, notification preferences, deployment, staging or production operation.
- Do not refactor unrelated routing, game, attendance, account or Officer
  publishing behaviour.

## Verification budget

Writer runs exactly the affected Flutter tests:

```text
flutter test test/notification_center_test.dart test/basic_app_test.dart test/production_demo_test.dart
flutter analyze <affected implementation and test files>
dart format --output=none --set-exit-if-changed <owned Dart files>
git diff --check
git status --short
```

Flutter Domain review is read-only and limited to capability gating, terminal
session/logout, Person switching and offline cache truthfulness. Main Work
reviews the actual diff, request single-flight and badge/read-state integration.
Hosted CI is the only full Flutter gate. Do not run PostgreSQL, backend,
emulator, staging or acceptance orchestration.

Evidence reuse requires exact HEAD, command/toolchain and relevant artifact
fingerprint. Correction budget is one batched round; correction verification is
delta plus adjacent lifecycle invariants only.

## Acceptance

- A capable signed-in Basic/Officer/Admin user can open the notification centre
  from the real home screen and see the correct unread count.
- Single and mark-all-read update both centre and home badge without duplicate
  requests or optimistic success after failure.
- Offline mode displays only valid cached content and disables all mutations.
- Capability/session/Person loss removes access and purges stale notification
  state without exposing another principal's content.
- The fake demo shows the same production widgets without network, credentials
  or external services.

## Status

- 2026-08-22: planned by Main Work and authorized for repository execution.
- 2026-08-22: Writer implementation and focused verification completed; Main
  and Flutter Domain lifecycle review findings were corrected on exact HEAD
  `ba52e21caa181ba456cdb72bc729c981e7b9c3af`.
- Current: source accepted; hosted Flutter gate pending.
