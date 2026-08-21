# TASK-142: Flutter game-list pull to refresh

- Task type: delivery
- Delivery group: `flutter-game-list-pull-refresh`
- Risk level: L1
- Base: `6e1e52795e593d736764e29c2819dc62111b1ee4`
- Owner gate: none

## Role claim

- claim_id: `task-142-flutter-writer`
- lease_version: 1
- actor_id: `01a013a7-7fde-7363-9314-7a255e8206a5`
- role: `codex-writer`
- scope: add an online-only pull-to-refresh gesture to the existing game list
- owned paths:
  - `clients/flutter_app/lib/basic_app.dart`
  - `clients/flutter_app/test/basic_app_test.dart`
  - `docs/coordination/reports/TASK-142-FLUTTER-CODEX.md`
- write: true, limited to the owned paths
- report_to: `main-work`
- stop_only_on: scope conflict, unrelated dirty state, auth/cache/API behavior change, unavailable exact Flutter toolchain, or a failing invariant that cannot be corrected within one bounded round

The same `claim_id` and `lease_version` may be acknowledged only once and must
not restart work or verification. No Domain Work is assigned for this L1 task.

## Goal

Let an online authenticated user refresh the game list with the conventional
pull-down gesture, including when the list is empty, while retaining the
existing refresh button and all current auth/cache boundaries.

## Scope and invariants

- Reuse the existing Basic reload callback; do not add API routes, persistence,
  auth/session behavior, background work or attendance mutation.
- Online game lists expose one pull-to-refresh action with a localized safe
  semantic label. One gesture starts at most one existing reload operation;
  overlapping input must not create concurrent requests.
- Empty online lists remain pull-scrollable so the gesture is available.
- Offline lists expose no enabled pull refresh and remain read-only.
- Existing button refresh, chronological ordering, account/status navigation,
  Officer report guard, error handling, cache reconciliation and logout guards
  remain unchanged.

## Verification budget

- Writer: self-review against the invariants, exact formatter check for changed
  Dart files, Flutter analyze, and focused `basic_app_test.dart`; no local full
  Flutter suite or emulator.
- Main Work: one diff/invariant review plus only the targeted regression needed
  to resolve a concrete finding.
- Hosted CI: one final Flutter workflow after Main accepts the diff.
- Correction budget: one bounded round. Runtime dogfood, staging, login and the
  quarantined acceptance harness are not gates.

## Acceptance

- Online non-empty and empty lists can each trigger exactly one existing reload
  through pull-to-refresh.
- A pending reload cannot be duplicated by another pull gesture or the existing
  button.
- Offline presentation contains no enabled pull-to-refresh action and performs
  no transport call.
- Focused tests, analyze, formatting and final hosted Flutter CI pass with no
  out-of-scope diff.
