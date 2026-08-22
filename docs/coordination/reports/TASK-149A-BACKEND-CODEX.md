# TASK-149 Slice A Backend Codex report

- Branch: `codex/task-149a-profile-pending-api-writer`
- Base: `d15cb46cae0cea60ac5eb9a3703c9f80529bda03`
- Scope: Mobile API self display-name mutation and pending LINE review credential contract; no schema, migration, Flutter, deployment, Secret/IAM, or production change.

## Delivered

- `PATCH /api/v1/me` updates only the authenticated active Person through the existing lifecycle validation, transaction and append-only audit. The raw idempotency key is hashed; exact replay is identified and a different canonical payload conflicts.
- Pending LINE exchange returns HTTP 202 with a ten-minute, purpose-separated review credential and no access token, refresh token or mobile session. Review endpoints can read only that identity's pending status/messages and append an applicant message through the existing bounded lifecycle service.
- Normal session authentication rejects review credentials. Each review request revalidates pending status; linked, blocked, disabled and expired credentials fail closed and require fresh normal authentication.
- Canonical OpenAPI and route/shared security tests cover the new surface and redaction boundaries.

## Verification

- `python -m unittest discover -s apps/mobile_api/tests -v`: 37 passed.
- `python -m unittest shared_lib.tests.test_mobile_api_service -v`: 16 passed.
- Installed-consumer `python -m unittest apps.mobile_api.tests.test_app apps.mobile_api.tests.test_openapi_contract -v`: 26 passed after rebuilding/installing `shared_lib-0.0.1`.
- `python -m compileall -q apps/mobile_api shared_lib/shared_module`: passed.
- `python -m json.tool apps/mobile_api/openapi.json`: passed.
- Black CLI and batch formatter API stalled in the documented bundled-Windows failure mode; formatting was checked/adjusted per file and hosted CI remains the final formatter evidence.
- No external application, cloud, database, notification or deployment effect occurred. Local-only effects were installing pinned test dependencies and the rebuilt shared package into the bundled runtime.
