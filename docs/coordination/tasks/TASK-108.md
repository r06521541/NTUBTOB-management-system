# TASK-108：Mobile authentication and API contract

task_type: planning
delivery_group: mobile-auth-api-foundation
requires_independent_pr: false
status: completed
owner: main_work

## Goal

Define one versioned, server-owned mobile authentication and JSON API contract
for the Flutter client before either client or backend runtime implementation.
Correct the native LINE Login handoff using current official guidance, map the
existing five attendance replies to stable public names, and specify session,
authorization, idempotency, retry, and safe notification-result semantics.

## In scope

- Define native LINE token assertion and server verification boundaries for an
  existing `AuthIdentity -> Person` principal.
- Define short-lived access sessions and opaque, rotating, device-bound refresh
  sessions, including expiry, revocation, and replay handling.
- Define `/api/v1` contracts for auth exchange/refresh/logout, current principal,
  games, game detail, and own attendance mutation.
- Define public attendance enum names and their compatibility mapping to the
  existing repository values without exposing database integers to clients.
- Define capability, error envelope, request ID, idempotency, retry, pagination,
  and timezone rules.
- Require attendance mutation to call the TASK-106 server-owned application
  service without duplicating changed or urgent-notification decisions.
- Add the minimum long-lived decision update required to supersede the earlier
  native authorization-code assumption.

## Out of scope

- Runtime API, LINE SDK integration, token issuance code, database tables,
  schema/migration/model/SQL, staging hosting, production deployment, or Secret.
- Google/Apple linking, account recovery, push provider, notification/audit
  schema, Officer/Admin notification mutation, and production role cutover.
- Production data, IAM, Scheduler, cloud resources, real notifications, release
  signing, APK/TestFlight upload, or store publication.

## Execution checkpoint

1. Goal: freeze a reviewable mobile auth/API contract shared by Flutter and the
   backend before implementation.
2. Core files: this task, one mobile API contract/planning artifact, DEC-097,
   and the existing Flutter plan/status indexes only when needed.
3. Invariants: Person remains the principal; server enforces every capability;
   native LINE credentials are verified rather than trusting profile fields;
   attendance rules remain in TASK-106; no runtime/schema/Secret mutation.
4. Tests: evidence mapping against current repository callers/tests, OpenAPI or
   equivalent structural validation, examples for success/failure/retry, docs
   links/numbering/budget checks, and `git diff --check`.
5. Blockers: refresh/device/idempotency persistence and staging hosting are
   implementation decisions for a later task; they must not be hidden behind
   in-memory production behavior in this planning task.

## Acceptance

- Flutter and backend reviewers agree on the same request/response and security
  boundaries; unresolved implementation choices are explicit.
- Native LINE Login no longer assumes that the Flutter SDK returns a browser
  authorization code; the accepted assertion and verification path cites
  official LINE guidance.
- The five attendance replies, `changed`, idempotency, retry, authorization,
  and post-persistence notification failure are unambiguous and tested through
  examples or contract checks.
- No runtime, schema, credential, endpoint deployment, or production behavior
  changes are present.
