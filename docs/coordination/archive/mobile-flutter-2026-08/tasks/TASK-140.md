# TASK-140: Flutter schedule refresh and readable game timing

- Task type: delivery
- Delivery group: `flutter-schedule-usability`
- Operator: agent under DEC-098
- Owner gate: LINE login/consent only, and only if a later optional runtime smoke reaches the logged-out gate

## Goal

Make the existing authenticated game list useful for routine use: present game
times in a readable local form, keep ordering deterministic, and let an online
user explicitly refresh without restarting or re-authenticating the app.

## Scope and path ownership

- Main Work owns this task, the minimal `PROJECT_STATE.md` closeout delta and
  singleton `HANDOFF.yaml`.
- The sole implementation writer owns
  `clients/flutter_app/lib/basic_app.dart`, its direct widget tests and one
  TASK-140 report.
- API routes, JSON contracts, auth/session handling, attendance mutation,
  Officer report behavior, backend/schema, staging fixtures and launcher source
  are read-only dependencies.

## Product invariants

- The list remains server/cache sourced and capability neutral; presentation
  must not invent games, mutate attendance or expose management data.
- Games are displayed in deterministic chronological order without mutating the
  caller-owned list.
- UTC contract timestamps are rendered through Flutter's local Material date
  and time presentation. Raw ISO timestamps are no longer the primary UI.
- Online refresh performs one existing Basic reload operation and cannot start
  a login, logout or attendance mutation. Offline mode remains read-only and
  exposes no enabled refresh action.
- Existing cache reconciliation, error states, role isolation, debug-only
  projections and logout purge remain unchanged.

## Harness asset policy

- Reuse the accepted atomic launcher, signer/session-preserving install,
  governed redacted JSON, no-disclosure broker and checkpoint primitives when
  they materially reduce manual work.
- `Invoke-MobileStagingAcceptance` full orchestration, its Resume observation
  path and UIAutomator timing retries are experimental/manual-on-demand. They
  are not a TASK-140 release gate.
- TASK-133 repository/hosted evidence is accepted; its E2E dogfood remains
  inconclusive because standalone status can pass while full Resume observation
  intermittently returns `STATUS_UNAVAILABLE`. The existing
  `await_observation` checkpoint is retained and must not be retried by this
  task.

## Leverage check

The writer may directly include one reversible, same-scope improvement that
clearly lowers later maintenance or test cost. It must be called out in the
checkpoint/report and covered by the same affected verification. Anything that
changes API/schema/auth/runtime mutation or expands the delivery group returns
to Main Work first.

## Acceptance and verification budget

- Direct widget tests cover chronological copy-safe ordering, readable local
  date/time, exact-one online refresh, disabled offline refresh and unchanged
  Basic/Officer isolation.
- Writer: one affected complete Flutter verification after early invariant
  self-review.
- Flutter Domain: one targeted review of refresh concurrency, presentation and
  auth/cache boundaries.
- Main Work: one integration-risk review; hosted CI is the final repository
  gate.
- Optional device smoke is one separately controlled use of atomic launcher
  actions after merge. It is evidence, not a merge prerequisite, and must not
  resume the quarantined TASK-133 orchestration.
