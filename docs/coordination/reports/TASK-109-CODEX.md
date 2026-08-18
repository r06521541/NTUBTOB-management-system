# TASK-109 Codex report

## Result

- Added expand-only Alembic revision `0005_mobile_auth_api_foundation` with the
  Owner-approved exact five tables, explicit constraints/indexes, RLS enabled
  with zero policies, and a local-rehearsal downgrade. No legacy table or
  attendance schema was changed.
- Added provider-neutral active-Person resolution, scoped future Game reads,
  Person-owned latest attendance readback, durable device sessions, rotating
  hashed refresh credentials, encrypted exact refresh-response replay,
  refresh-family replay revocation, current-device logout and durable mutation
  idempotency.
- Added an independent `apps/mobile_api/` Flask/Cloud Run deployment unit after
  Owner architecture approval. Bearer auth is separate from Web Portal
  cookie/CSRF state. Startup requires exact revision 0005 and runtime keys. The
  LINE adapter now uses LINE's official Verify ID token endpoint with
  `id_token`, Channel ID and nonce, a bounded timeout, safe errors and an
  injectable fully mocked HTTP port; fixed RS256/public-key configuration was
  removed. No deploy Make target was added and no build/deploy was run.
- Added Basic-only `/api/v1` auth, `me`, scoped Game list/detail, bounded replied
  attendance projection and own attendance mutation through TASK-106. Public
  attendance values are `attending`, `not_attending`, `arriving_late`,
  `leaving_early`, and `undecided`; only the server maps them to legacy 1..5.
- Added canonical `apps/mobile_api/openapi.json`, including transport locations,
  bounds/TTLs, nullable/required fields, opaque IDs, RFC3339, pagination,
  privacy, exact errors/examples, retry/idempotency and reconciliation rules.
  It intentionally excludes `expected_version`, pending polling, deep-link and
  notification endpoints.

## Security and failure review

- Raw LINE assertions, app refresh/access tokens, nonce, installation ID,
  refresh-attempt ID and idempotency key are not persisted or logged. Database
  state contains hashes; the lost-response envelope is encrypted through an
  injected cipher. Runtime missing signing/encryption/audience config fails
  closed. LINE 4xx assertions fail authentication; 429 and 5xx/timeout are
  bounded retryable errors, with no provider body or token in logs/errors.
- Same refresh attempt replays the exact encrypted access/refresh response.
  Reuse from another attempt, including a concurrent race, commits family
  revocation before returning conflict. Logout affects only the current device.
- Attendance idempotency now durably claims before mutation, serializes execution
  on the claim, and finalizes only after authoritative attendance readback.
  Finalize/response-construction failure reconciles a saved reply without
  repeating mutation or notification. A later process recovering a pending
  claim reports `changed=null` and notification `unknown` rather than inventing
  the lost outcome; that truthful result is then durable for subsequent exact
  replay. Different-body reuse remains `idempotency_conflict`. TASK-106 still
  owns commit-before-best-effort-notification; `changed=false` never notifies.
- Basic attendance returns only People who replied and omits unreplied roster,
  provider subjects, contact data, member metadata, admin notes and audit data.
  Missing/cancelled/past/non-invited Games remain outside the scoped read model.
- No Flutter, Officer/Admin API, production data, external HTTP, Secret, IAM,
  Scheduler, notification, deployment or cloud operation occurred.

The LINE correction follows LINE's official native-server guidance:
`https://developers.line.biz/en/docs/line-login/verify-id-token/` and
`https://developers.line.biz/en/docs/line-login-sdks/android-sdk/managing-users/`.
No request to that endpoint was made during implementation or verification.

## Verification

- `apps/mobile_api/tests`: 14 passed (route/error/revision gates, official LINE
  verify request/response, audience/nonce/expiry, 4xx/429/5xx/timeout and safe
  redaction, OpenAPI/deployment contract).
- `shared_lib/tests`: 19 passed (TASK-106 plus mobile auth/Basic API service).
- `apps/web_portal/tests`: 185 passed, 2 skipped.
- `functions/line_webhook_handler/tests`: 26 passed.
- Portal-data targeted static/in-memory suite: 21 passed, 26 PostgreSQL cases
  skipped in that offline invocation; the task-specific PostgreSQL cases were
  run separately against both versions as listed below.
- PostgreSQL 15.8 and 16.4 isolated local containers: legacy setup, upgrade to
  0005, downgrade to 0004, re-upgrade to 0005, model/column parity, five-table
  RLS, refresh race/rotation/exact replay/family revoke/expiry/logout and
  idempotency replay/conflict/concurrency/finalize recovery: 8 passed on each
  version.
- Migration graph and Phase C artifact compatibility targeted suite: 12 passed.
- Bundled Python `py_compile`, Black 24.4.2 check, isort Black-profile check,
  OpenAPI JSON parse and `git diff --check` passed.

Full Windows portal-data discovery executed 230 tests. All task-related and
database lifecycle cases progressed after adding 0005-aware test reset
isolation; the run still ended with 35 existing checksum-artifact errors because
this managed Windows checkout materializes unchanged Phase B/identity SQL
artifacts with non-canonical line endings. Those artifacts are outside this
task, absent from the diff, and were not regenerated. Hosted Python 3.10/Linux
CI remains required for the canonical checksum gate and the static Cloud build
context; no Docker image was built.

## Handoff

- Branch: `codex/task-109-mobile-auth-api-foundation`
- Base: `29c4b304193bb870f565848ad587c5735c017b74`
- Implementation commit: `b5464bd7cc41fd981548eed28bed4712b08c56d5`
- Report: `docs/coordination/reports/TASK-109-CODEX.md`
- Next actor: Main Work review; no PR created.
