# TASK-109：Mobile auth and Basic API foundation

task_type: delivery
delivery_group: mobile-auth-api-foundation
requires_independent_pr: true
status: completed
base_commit: 87100faec55aef47f7c9fda1b6b1c47c79dd6c1a

## Goal

Implement the approved TASK-108 native LINE assertion and `/api/v1` Basic
contract with durable device sessions, refresh rotation/replay protection and
exact mutation idempotency. Add only the minimum Person/game read helpers and
route adapters needed for `me`, games, own attendance readback and attendance
mutation.

## Proposed schema revision

Alembic `0005_mobile_auth_api_foundation`, expand-only:

1. `mobile_sessions`: one server-owned device session; references linked
   `auth_identity` and `person`, stores only opaque IDs/hashes, status, access
   epoch, refresh-family expiry, revocation and bounded timestamps.
2. `mobile_refresh_tokens`: hashed refresh credentials and generations per
   session, with current/rotated/revoked state, successor relation, rotation
   time and bounded replay-grace metadata. Raw tokens are never stored.
3. `mobile_refresh_attempts`: unique session + client attempt ID, request hash,
   bounded encrypted successor response and expiry so a lost successful
   rotation response can replay exactly. Encryption key is runtime Secret and
   is not created or read by this task.
4. `mobile_idempotency_records`: principal/session + method + canonical route +
   idempotency key, request hash, terminal HTTP status/body and expiry. Same key
   with different request fails; terminal results replay exactly.
5. `mobile_auth_exchanges`: bounded hash of accepted provider assertion and
   login-attempt ID with expiry, preventing a successful native ID-token
   exchange from creating multiple sessions through replay.

All five tables use explicit constraints/indexes, RLS enabled with zero policy,
no grants, no trigger and no provider token/profile payload. Production rollout
is not part of this task.

## Runtime scope after schema approval

- Provider-neutral linked-identity/active-Person resolver.
- Person-based latest Game attendance reply helper and scoped Game projections.
- Native LINE ID-token verifier port with mocked offline tests; no real LINE
  request or Secret in tests.
- App access token issue/verify, refresh rotation, current-device logout and
  replay-safe transactions.
- `/api/v1/auth/line/exchange`, `/auth/refresh`, `/auth/logout`, `/me`, `/games`,
  `/games/{id}`, `/games/{id}/attendance`, and own attendance mutation through
  TASK-106.
- Basic capability only. Officer/Admin report and notification endpoints remain
  deferred.

## Invariants

- No raw LINE ID/access token, App refresh token, nonce, profile, secret or
  plaintext credential is persisted or logged.
- Production Admin allowlist and bounded Officer behavior remain unchanged.
- Attendance transaction and urgent notification behavior remain owned by
  TASK-106; API idempotency cannot make a saved reply look failed.
- Old Web/LINE services continue to run safely before migration and during
  rollout; new API runtime requires revision 0005 and fails closed otherwise.
- Downgrade is local rehearsal only. Production rollback disables/reverts the
  new runtime while retaining expand-only tables and data.

## Verification

- Migration upgrade/downgrade and model/constraint parity on PostgreSQL 15/16.
- Token hashes only, refresh race/replay/lost-response, revocation, expiry and
  idempotency concurrency tests.
- LINE assertion wrong audience/nonce/expiry/replay tests with offline verifier.
- Basic authorization, scoped reads, all five replies, unchanged/no-notify and
  notification-failure truthful response tests.
- Existing Web/LINE/full portal-data suites, Python 3.10 hosted CI, formatter,
  diff/status and deployment-package checks.

## Owner approval gate

Owner approved revision 0005 and the exact five-table schema boundary on
2026-08-18. This task does not authorize production migration, Secret
creation/binding, deployment, real LINE verification, production data or
notifications.
