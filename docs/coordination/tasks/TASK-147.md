# TASK-147: Flutter notification destination navigation

- Task type: delivery
- Delivery group: `mobile-notification-destinations`
- Risk level: L2 authorization／navigation／offline state
- Repository authority: `4c6993ed5dbbde3919643ffa56bd5ae419e7f0fc`
- Owner gate: none for repository work; deployment, staging, Secret/IAM,
  provider/data, signing and stores remain excluded

## Goal

Complete the in-app half of the typed notification destination contract. A
capable signed-in user can open a notification and reach its notification
detail or an already-authorized game, while unknown or unauthorized targets
fail safely inside the notification centre.

## Writer claim

- claim_id: `task-147-flutter-notification-destinations-writer`
- lease_version: 1
- actor_id: `01a028df-f8d8-7d23-b91f-6fe97c4ad395`
- role: `codex-writer`
- write: true, limited to the task's Flutter implementation, affected tests and
  `docs/coordination/reports/TASK-147-FLUTTER-CODEX.md`
- report_to: `main-work`
- implementation branch: `codex/task-147-notification-destinations-writer`

## Scope

- Wire `NotificationCenter.onOpen` through the real `BasicGamesView`
  composition.
- Resolve only the existing typed `notification`, `game` and list-fallback
  destinations; do not accept arbitrary routes or URLs.
- Show notification detail from the already loaded/cached item without an
  extra transport request.
- Open a game only when its ID exists in the current principal's loaded game
  collection; otherwise remain in the centre with truthful feedback.
- Preserve read-state behaviour: online unread items perform the existing
  guarded mark-read operation, while offline cached items navigate read-only
  with zero mutation.
- Cover real composition and production-shaped fake demo navigation with
  deterministic widget tests.

## Invariants and non-goals

- `notifications:read` remains the entry and route capability boundary.
- A destination payload cannot reveal or fetch a game absent from the current
  principal's authorized game collection.
- Unknown, malformed or unauthorized destinations never become arbitrary
  Navigator routes and never trigger speculative network calls.
- Terminal session, logout, Person switch, capability loss and cache
  invalidation behaviour from TASK-146 must remain unchanged.
- No OS push/deep-link entry, FCM/APNs, LINE/Discord, backend, OpenAPI, schema,
  migration, deployment, emulator, staging, signing or store work.

## Verification budget

Writer runs focused notification/basic/demo widget tests, analyze and formatter
checks for affected Dart files, then `git diff --check` and `git status --short`.
Main Work reviews the actual routing and authorization diff. Flutter Domain
review is added only if the implementation changes a lifecycle or capability
boundary; otherwise Hosted CI is the sole full Flutter gate. No backend,
PostgreSQL, emulator or runtime matrix.

Evidence reuse requires exact HEAD and unchanged command/toolchain. One batched
correction round is allowed; corrections rerun only the affected slice and
adjacent authorization/navigation invariants.

## Acceptance

- Tapping a notification destination opens its in-app detail from current
  state without an extra fetch.
- Tapping an authorized game destination opens the existing game detail view.
- Missing/unauthorized games and malformed destinations stay safely in the
  notification centre with understandable feedback and zero speculative I/O.
- Offline cached notifications may open cached detail or cached authorized
  games, but never perform read mutations.
- Existing logout/session/capability/cache lifecycle tests continue to pass.

## Status

- 2026-08-22: planned by Main Work and authorized for repository execution.
- Current: ready for Writer claim.
