# TASK-141: Flutter account and data status page

- Task type: delivery
- Delivery group: `flutter-account-data-status`
- Operator: agent under DEC-098
- Owner gate: none for repository delivery

## Goal

Give an authenticated or offline user one clear, privacy-safe place to understand
which account is being presented, when game data was last synchronized and
whether the current view is fresh server data or offline read-only cache.

## Scope and ownership

- Main Work owns this task, `PROJECT_STATE.md` and singleton `HANDOFF.yaml`.
- One implementation writer owns the minimum Flutter source, its direct widget
  tests and one TASK-141 report.
- Backend/API/schema, auth/session lifecycle, attendance, Officer report,
  launcher/harness and notification settings are read-only dependencies.

## Invariants

- The page is reachable only from an already authenticated or offline Basic
  shell; it cannot initiate login, logout, refresh, mutation or navigation to an
  unauthorized management route.
- Public presentation may use the existing display name, localized last-sync
  time and authoritative/offline provenance wording. It must not render Person
  ID, access-level/capability internals, provider subject, token/session data,
  endpoint, storage/cache key or debug projection.
- Offline state is explicitly read-only and non-authoritative. Fresh state is
  described as server-synchronized without claiming exact request status.
- Existing game list refresh, logout race guards, offline behavior and
  Basic/Officer authorization remain unchanged.

## Leverage check

The writer may include one reversible same-scope accessibility or presentation
helper when it removes duplicated formatting and is directly tested. No new
settings toggle or persisted preference may be invented.

## Acceptance and budget

- Widget tests cover fresh/offline content, navigation, semantic labels,
  sensitive-value exclusion and unchanged management isolation.
- Writer runs one affected complete Flutter verification after early privacy
  and navigation self-review.
- Flutter Domain runs one targeted privacy/navigation review; Main performs one
  integration-risk review; hosted CI is the final gate.
- No emulator or staging runtime is required. Any later smoke uses only accepted
  atomic launcher actions and is not a merge prerequisite.
