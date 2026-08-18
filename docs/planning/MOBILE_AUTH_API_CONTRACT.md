# Mobile authentication and API v1 contract

Status: `approved` (Owner, 2026-08-18; TASK-108)  
Runtime implementation: none

This document freezes the first mobile contract for later backend and Flutter
implementation. It does not authorize schema, Secret, staging, production, or
external LINE operations.

## 1. Protocol invariants

- Base path is `/api/v1`; JSON is UTF-8 and clients ignore unknown response
  fields. Public IDs are opaque strings. Times are RFC 3339 UTC instants;
  display uses Asia/Taipei.
- Every response includes `X-Request-ID`. Cursors are opaque and lists use
  `{ "items": [], "next_cursor": null }`.
- The authenticated principal is an active `Person` reached through a linked
  identity. UI visibility never substitutes for server authorization.
- Production Admin continues to follow DEC-082. Persisted Officer/Admin access
  is not enabled globally by this contract.

## 2. Native LINE exchange

`POST /api/v1/auth/line/exchange`

The Flutter client requests `openid`, creates a cryptographically random nonce,
passes it explicitly to the native LINE SDK, and sends:

```json
{
  "id_token": "raw LINE ID token",
  "nonce": "original login nonce",
  "login_attempt_id": "client opaque random identifier",
  "device": { "installation_id": "opaque random identifier", "platform": "android" }
}
```

The server verifies the raw ID token with the configured LINE channel,
including issuer/signature, expiry, audience and nonce, and uses only verified
`sub` as `provider_subject`. Client profile, display name, user ID and channel
ID are never identity assertions. Missing, malformed, expired, wrong-audience,
wrong-nonce, stale or replayed assertions fail without creating a session.

Native LINE SDK owns its provider redirect flow. Browser authorization code,
PKCE verifier and redirect URI are not part of this native contract. A future
custom browser flow requires a separate contract.

The server resolves a provider-neutral linked identity and requires an active
Person. Pending identity returns `identity_pending`; rejected, ignored,
disabled or blocked identities do not authenticate. Inactive, disabled or
blocked People do not receive an app session. Successful exchange returns the
same session envelope as refresh.

## 3. App session lifecycle

The backend issues a short-lived app access token and an opaque, device-bound,
rotating refresh token. These are not LINE provider tokens.

```json
{
  "access_token": "opaque-or-signed app token",
  "access_expires_at": "2026-08-18T10:15:00Z",
  "refresh_token": "opaque app refresh token",
  "refresh_expires_at": "2026-09-17T10:00:00Z",
  "session_id": "opaque",
  "person": {},
  "capabilities": []
}
```

- Access token exists only in memory. Refresh token exists only in Android
  Keystore-backed storage or iOS Keychain.
- `POST /auth/refresh` rotates refresh tokens. `Refresh-Attempt-ID` makes a lost
  successful response safely replayable for a bounded grace period; later reuse
  from another attempt is replay and revokes the token family.
- Concurrent 401 responses share one refresh. A request is retried at most once.
  403 never refreshes.
- `POST /auth/logout` idempotently revokes only the current device session.
  200, 204 or already-unauthenticated clears local session. On transient network
  failure the client enters `logout_pending`, blocks authenticated UI, preserves
  the encrypted refresh token only to retry revocation, and does not claim logout
  completed.
- Rotation, device sessions and replay detection require durable persistence.
  No production implementation may replace it with process memory.

## 4. Initial read endpoints

- `GET /me`: Person display data, optional Member summary, status-safe public
  fields and server-computed capabilities.
- `GET /games?cursor=&limit=`: scoped upcoming games and the caller's current
  reply. Limit is bounded by the server.
- `GET /games/{game_id}`: scoped game detail, caller reply and typed deep-link
  targets; a new application read service must own this projection.
- `GET /games/{game_id}/attendance`: Basic sees only People who replied;
  authorized Officer/Admin may receive the bounded fuller projection.
- `GET /games/{game_id}/attendance-report`: Officer/Admin capability only.

The backend needs a Person-based current-reply helper. Existing team summaries
cannot provide caller readback because their projection may omit guest reply 5.

## 5. Attendance mutation

`PUT /games/{game_id}/attendance-reply`

Request:

```json
{ "reply": "arriving_late", "expected_version": "opaque-or-null" }
```

Public enum and legacy mapping:

| Public value | Existing value | Meaning |
| --- | ---: | --- |
| `attending` | 1 | 能到 |
| `not_attending` | 2 | 不到 |
| `arriving_late` | 3 | 晚到 |
| `leaving_early` | 4 | 早走 |
| `undecided` | 5 | 未定 |

Only the server maps these values or computes participation groupings. Unknown
values fail closed. The endpoint must invoke the TASK-106 application service.

```json
{
  "game_id": "opaque",
  "reply": "arriving_late",
  "changed": true,
  "updated_at": "2026-08-18T10:00:00Z",
  "notification": { "status": "succeeded" }
}
```

Notification status is `not_required`, `succeeded`, or `failed`. A notification
failure after persistence remains a successful attendance response and exposes
only a bounded code. `changed=false` is successful and never notifies.

## 6. Idempotency and retry

Every mutation carries `Idempotency-Key`, generated once per user-confirmed
logical action and reused for timeout retry. Server scope is principal/device,
method and canonical route. It durably stores request hash and terminal result:

- same key + same request replays the same response;
- same key + different request returns `idempotency_conflict`;
- retention must exceed the documented maximum client retry window.

Exact response replay requires durable persistence. State-idempotent attendance
alone is insufficient evidence for an unknown network result. After timeout the
client shows「送出結果確認中」, reconciles the server state, and retries with the
same key only when needed. It never displays an unconfirmed mutation as success.

Automatic retry is limited to connection failure, 408, 429 with Retry-After, or
explicitly retryable 5xx, using bounded exponential backoff and jitter.

## 7. Error envelope

```json
{
  "error": {
    "code": "validation_failed",
    "message": "無法處理這次要求。",
    "request_id": "opaque",
    "retryable": false,
    "retry_after_seconds": null,
    "field_errors": []
  }
}
```

- 400 malformed transport; 401 `unauthenticated`/`session_expired`;
  403 `forbidden`; 404 `resource_not_found` without existence leakage;
  409 `idempotency_conflict` or `state_conflict`; 422 `validation_failed`;
  429 `rate_limited`; 503 `service_unavailable`; other 5xx `server_error`.
- Provider or internal exception bodies, tokens and secrets are never returned.
- 403/404/409/422 are not automatically retried.

## 8. Deferred contracts and implementation gates

Notification centre/publishing, push token lifecycle, Google/Apple linking and
production Officer resolver remain deferred. Deep links, when added, use typed
`{type, resource_id, action?}` targets and never arbitrary server URLs.

Backend implementation cannot start until Main Work explicitly decides the
durable store and migration/rollback for refresh families, devices and exact
idempotency replay. Staging must use isolated data and endpoint/Secret bindings.
Android minimum version remains undecided and must be pinned at least to the
selected LINE SDK requirement; iOS runner currently targets 15.0 but requires a
macOS/Xcode build before becoming support policy.

## 9. Acceptance cases

- Valid ID token/audience/nonce succeeds; malformed, expired, wrong audience,
  wrong or missing nonce and replay create no session.
- Only verified `sub` selects identity; spoofed profile fields have no effect.
- Refresh covers rotation, lost-response replay, token-family replay revocation,
  concurrent 401 single-flight and terminal session expiry.
- Logout covers success, already revoked, transient failure and restart while
  `logout_pending`.
- Capability matrix is enforced per endpoint and Basic never receives unanswered
  names.
- Five public reply values round-trip bijectively; unknown values fail closed;
  unchanged and notification-failure outcomes remain truthful.
- Idempotency covers same-key replay, payload conflict and timeout reconciliation.

## 10. Official LINE references

- Native secure login: https://developers.line.biz/en/docs/line-login/secure-login-process/
- Android raw ID token and nonce: https://developers.line.biz/en/docs/line-login-sdks/android-sdk/managing-users/
- LINE Login API token verification: https://developers.line.biz/en/reference/line-login/
