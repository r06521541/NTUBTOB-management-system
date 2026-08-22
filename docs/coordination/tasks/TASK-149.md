# TASK-149: Flutter phase-one no-schema parity completion

- Task type: delivery
- Delivery group: `mobile-phase-one-no-schema-parity`
- Risk level: L3 API/auth contract plus L2 client state/offline
- Repository authority: `598f522475bfb9102ff21bb697eb5cc4ea9eb03b`
- Owner decisions: pending-identity conversation enabled; notification permission
  and system-settings actions enabled only after an explicit user tap; manual
  light/dark/system theme enabled; two execution slices with one final PR
- Owner gate: none for repository implementation; schema/migration, provider,
  Secret/IAM, deployment, real notification, signing and stores remain excluded

## Goal

Complete the remaining no-schema Flutter phase-one member experience in one
delivery: self-service display-name editing, pending-identity conversation,
next-game home actions, scalable notification browsing, onboarding and local
app preferences. The Mobile API remains the server-owned authorization and
mutation boundary.

## Delivery structure

### Slice A: Mobile API and shared application service

- Add an authenticated self-profile display-name mutation. It may update only
  the current active Person and must reuse the existing server validation,
  transaction and append-only audit boundary.
- Require an idempotency key. Exact key/payload replay is safe and identifiable;
  reuse with a different display name fails with the canonical conflict error.
  Do not store or log a raw client key.
- Return the canonical refreshed Person projection needed by Flutter plus
  truthful changed/replayed state.
- Add a bounded pending-identity review contract. A pending native LINE
  exchange may issue only a short-lived, single-purpose review credential; it
  must not issue a normal mobile session or grant games/notification access.
- The review credential may read only its own review status/messages and append
  one bounded applicant message. It cannot approve, reject, link, remap, ignore,
  unblock or inspect another identity.
- Terminal linked/blocked/disabled/expired states fail closed and direct the
  client to repeat normal authentication as appropriate.
- Update canonical OpenAPI, Mobile API/shared tests and redaction/error
  contracts. Reuse existing tables and lifecycle services; no DDL or migration.

### Slice B: Flutter client and production-shaped fake demo

- Add display-name editing to the account experience with input validation,
  one logical idempotency key per confirmed intent, retry-safe unknown outcome,
  refreshed root Person and principal-scoped offline cache after success.
- Add the pending-identity status/conversation screen. It can read and append
  only through the single-purpose review credential and must never render the
  authenticated home until a fresh normal login succeeds.
- Add a next-game home card using already authorized games and attendance data:
  own reply, quick game detail/reply entry, loading/empty/error/offline and
  last-sync truthfulness. Do not add weather or speculative requests.
- Complete notification browsing with all/unread filters and cursor-based load
  more. Preserve TASK-146/147 badge, read state, destinations, principal cache,
  single-flight and offline read-only invariants; do not eagerly fetch every
  page.
- Add a skippable 2-3 page first-run onboarding using production visual
  components. Completion is installation-local and does not contain identity
  data.
- Add local theme preference: system/light/dark. Persist only the preference;
  do not bind it to a Person or server record.
- Add notification guidance with an explicit user action to request OS
  permission and, when denied, another explicit action to open system settings.
  Never prompt on launch or infer success. In-app notifications remain usable.
- Extend the production-shaped fictional demo with deterministic normal,
  pending, offline, paging and settings scenarios using the same production
  widgets and no network/credentials.
- Correct the root `.gitignore` nested `lib/` match so new Flutter library files
  are normally trackable while the intended repository-root `lib/` output
  remains ignored. Add a focused contract test if an existing repository gate
  supports it.

## Security and product invariants

- Flutter never chooses authorization from a role label or local preference.
- Pending-review authority is not an authenticated Person session and cannot be
  upgraded client-side.
- Only `display_name` is editable. Formal name, contact, access level,
  qualifications, identities, admin note and status remain server-controlled.
- No Person, provider subject, token, review credential, notification content
  or idempotency key is logged or exposed in diagnostics.
- Offline mode is read-only for profile, attendance, review messages and
  notifications. Theme/onboarding preference remains local-only.
- No arbitrary URL/deep link, external contact, analytics or clipboard action.
- No people/qualification/access administration, identity approval/remap,
  Lineup Lab, insights, weather, Admin pinning, Google/Apple auth or account
  recovery.
- No schema, migration, real APNs/FCM, provider token, Secret/IAM, cloud
  mutation, deployment, emulator, signing, TestFlight or store operation.

## Verification and acceptance budget

Slice A Writer runs affected Mobile API, OpenAPI and shared application-service
tests plus format/static checks and diff/status checks. Main reviews the actual
auth/idempotency/redaction contract. Hosted CI supplies the relevant backend and
PostgreSQL matrix selected by changed paths.

Slice B Writer runs affected Flutter tests, analyze/format and diff/status
checks. Existing Flutter Domain performs one read-only targeted review limited
to pending credential separation, profile/root/cache reconciliation,
notification pagination/offline state and explicit permission actions. Main
reviews the actual cross-slice invariant and composition diff. Hosted CI is the
only full Flutter gate; no local full suite or emulator.

Evidence is reusable only at exact HEAD and unchanged command/toolchain/matrix.
Each slice has one batched correction round; corrections rerun only their
affected delta and adjacent security/state invariant. A second unresolved P1 in
the same slice stops for Main/Owner scope decision.

## Completion

- A member can safely update only their own display name and sees the refreshed
  identity consistently online and in the next valid offline cache.
- A pending applicant can read and append only their own review conversation
  without obtaining authenticated app access.
- Home presents the next authorized game and own attendance state with truthful
  offline behaviour.
- Notification all/unread filtering and incremental pagination preserve badge,
  read and destination correctness without eager full-history reads.
- Onboarding, theme and notification-permission actions behave only as locally
  configured and explicitly initiated.
- One final ready PR passes change-selected Hosted CI. No excluded external
  operation occurs.

## Status

- 2026-08-22: expanded and authorized by Owner with all four product decisions.
- Current: Slice A ready for Backend Writer claim.
