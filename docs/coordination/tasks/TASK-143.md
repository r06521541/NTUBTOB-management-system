# TASK-143: Flutter readable game-detail metadata

- Task type: delivery
- Delivery group: `flutter-game-detail-metadata`
- Risk level: L1
- Base: `8895747502347f86d9611bad103a5680a2759db4`
- Owner gate: none

## Role claim

- claim_id: `task-143-flutter-writer`
- lease_version: 1
- actor_id: `01a013a7-7fde-7363-9314-7a255e8206a5`
- role: `codex-writer`
- scope: render existing game-detail schedule metadata with the same localized presentation as the game list
- owned paths:
  - `clients/flutter_app/lib/basic_app.dart`
  - `clients/flutter_app/test/basic_app_test.dart`
  - `docs/coordination/reports/TASK-143-FLUTTER-CODEX.md`
- write: true, limited to the owned paths
- report_to: `main-work`
- stop_only_on: scope conflict, unrelated dirty state, API/auth/cache behavior change, unavailable exact Flutter toolchain, or a failing invariant that cannot be corrected within one bounded round

The same `claim_id` and `lease_version` may be acknowledged only once and must
not restart work or verification. No Domain Work is assigned for this L1 task.

## Goal

Replace the raw ISO timestamp on the existing game detail page with the same
localized, readable date/time, location and duration presentation used by the
game list.

## Scope and invariants

- Reuse one presentation helper for the list and detail page so their metadata
  cannot drift.
- Render local Material date/time. Include non-empty location and available
  duration; omit absent optional values without placeholder invention.
- Keep team names, attendance read/write controls, authoritative reply state,
  API routes, DTOs, auth/session, cache and Officer behavior unchanged.
- Do not add dependencies, persistence, navigation, runtime diagnostics or
  staging actions.

## Verification budget

- Writer: early invariant self-review, package-context formatter check for the
  two owned Dart files, Flutter analyze, and focused `basic_app_test.dart` only.
- Main Work: one cumulative diff/invariant review; no Domain review.
- Hosted CI: one final change-selected Flutter gate after Main acceptance.
- Correction budget: one bounded round. No emulator, staging, login or
  acceptance-harness gate.

## Acceptance

- Game list and detail use the same formatter result for identical metadata.
- Detail output contains readable local date/time plus present location and
  duration, and does not expose the raw ISO timestamp as its primary copy.
- Missing location/duration are omitted cleanly.
- Existing attendance behavior and focused Flutter tests remain green.
