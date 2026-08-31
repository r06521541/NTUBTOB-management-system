# TASK-171 Mobile Auth writer report

- actor: `/root/task170_play_evidence_writer`
- claim: `task-171-mobile-apple-auth-writer-20260831` / lease 1
- branch: `codex/task-171-apple-auth-repository-slice`
- base: `8ae17853fa24379f6394ff3122c3eccb0be326ec`
- independent review input: `23b14876b3a4d1fb420badea683601d10dc4ca81`
- state: final correction ready for Main integration review; correction not committed

## Delivered

1. The canonical shared provider module now verifies Apple ID tokens with RS256 only. It strictly parses canonical base64url/JSON,
   verifies the exact Apple issuer/audience, bounded expiry/issued-at, stable ASCII `sub`, and token nonce equal to lowercase
   SHA-256 of the raw nonce received by Mobile API. Email, private relay email, name and real-user status are ignored and never enter
   `VerifiedAssertion`.
2. Apple public RSA keys use an HTTPS GET transport with a five-second timeout, 64-KiB response cap, 1–10 key cap and 15-minute
   thread-safe cache. JWKs must have exact `kty/kid/use/alg/n/e`, `RSA/sig/RS256`, canonical modulus/exponent, 2048–4096-bit modulus
   and exponent 65537. Duplicate kids, ambiguous/malformed keys and algorithm confusion fail closed. The cache permits at most one
   thread-safe early refresh for any unknown kid per fresh cache window; later same/different unknown kids do not call transport.
   Cold/expired refresh attempts establish a one-minute failure backoff before transport. Concurrent and sequential 5xx, timeout,
   malformed and oversized failures therefore make at most one request per backoff window; clock rollback cannot reopen the window.
   A successful refresh clears failure state. Normal TTL expiry starts a new bounded window and still supports signing-key rotation.
3. `/api/v1/auth/apple/exchange` accepts exactly `id_token`, raw `nonce`, `login_attempt_id`, `installation_id`, and iOS `platform`.
   It reuses the existing server-owned exchange/session/replay flow. Apple candidate/proof routes use the same token+raw-nonce shape
   plus the existing candidate fields; unknown profile fields are rejected before verification.
4. Identity linking now accepts Apple candidate/proof credentials while preserving purpose-separated five-minute proofs, explicit
   confirmation, different-provider proof, binding, replay/idempotency and conflict checks. A new Apple candidate is keyed only by
   `(provider='apple', verified sub)`, remains pending with no Person, and cannot auto-merge by email/name.
5. Linked identity labels include only the safe Apple label and timestamp. Existing LINE legacy handling remains LINE-only; Google and
   LINE verification paths and their exchange/link behavior are unchanged.
6. Bootstrap creates a nonce-required Apple auth service only for one exact, nonblank runtime `MOBILE_API_APPLE_AUDIENCE`. Missing,
   blank or surrounding-whitespace values leave `apple_auth=None`; Apple endpoints fail closed while existing LINE/Google startup and
   authentication remain available. The example intentionally disables Apple; no real identifier, key, client secret or provider
   configuration was added. OpenAPI freezes the optional runtime boundary, exact exchange/link shapes and sub-only privacy boundary.

## Verification

- `py -3.10 -m unittest discover -s apps/mobile_api/tests -v`: PASS, 64/64 tests. This includes nine real fictional-RSA Apple verifier
  cases, three Apple repository/link cases, optional-Apple bootstrap behavior, Apple exchange/candidate/proof route cases, OpenAPI,
  and all existing LINE/Google tests.
- `py -3.10 -m unittest tests.portal_data.test_mobile_api_foundation -v`: 15/15 skipped because no local
  `PORTAL_DATA_TEST_DATABASE_URL`; no PostgreSQL connection was attempted. Hosted PostgreSQL integration remains required.
- `py -3.10 -m py_compile ...`: PASS for every changed Python module/test. `openapi.json` also parsed successfully with the standard
  library JSON decoder.
- `py -3.10 -m isort <changed Python paths>` followed by `py -3.10 -m black <changed Python paths>`: applied in repository format
  order. The subsequent multi-file Black CLI check remained at high CPU in the documented Windows failure mode; all formatter
  processes started by this lane were terminated. Same-version `black.format_str` comparison over every changed Python path:
  `BLACK_API_OK`.
- `git diff --check`: PASS; Windows LF→CRLF warnings only.

## Test-first and self-review findings

- The Apple verifier test initially failed because no Apple adapter existed. Final tests cover cached success, one-refresh rotation,
  a concurrent same/different-unknown-kid refresh bound, normal TTL refresh, duplicate/ambiguous kid, wrong algorithm/key
  metadata/signature, wrong issuer/audience/nonce/expiry/subject, malformed/oversized JWT/JWK sets, noncanonical JWK integers and
  transport failures without assertion/body disclosure.
- Route tests prove email/name/user/real-user fields are rejected for exchange, and email is rejected for candidate/proof routes.
  Service/repository tests prove only verified `sub` reaches the Apple candidate lookup and a new candidate has `person_id=None`.
- Successful `VerifiedAssertion` and API/session responses contain no Apple email, name, real-user status, raw assertion or hashed nonce.
- Main's correction regression first demonstrated both defects: bootstrap required Apple configuration and each unknown kid could
  trigger another forced refresh. The final route/source tests prove optional Apple configuration preserves LINE, and the concurrent
  cache test proves transport stays bounded to one early refresh within the cache window while rotation and TTL refresh remain live.
- Independent Auth/Security review then demonstrated that cold/expired refresh failures were not negative-cached. The final regression
  covers concurrent plus sequential 5xx/timeout/malformed/oversized failures, a caller-time rollback, the exact one-minute deadline,
  data-leak resistance, successful recovery and early rotation. It first observed eight transports for eight concurrent requests and
  now proves one transport per backoff window without sleeps or retries.

## Remaining limits

- No real Apple audience/App ID, Developer account, JWK request, ID token, key/client secret, entitlement/profile, signing material,
  Secret, cloud/runtime, production, deployment or real user/device was accessed or mutated.
- Windows/local tests did not exercise a real provider, database, Xcode/archive, entitlement, app install or end-to-end sign-in.
- This slice does not receive an Apple authorization code, obtain an Apple refresh token, or handle provider revocation. Those remain
  future public-provider/runtime gates. Existing server-owned application refresh tokens are not Apple provider refresh tokens, and
  repository acceptance must not be represented as a complete provider-session lifecycle or provider/runtime readiness.
- The Apple public-key endpoint and exact audience remain future runtime bindings. Independent Auth/Security review and hosted CI on
  an immutable integrated SHA remain required.

## Exact changed paths

- `shared_lib/shared_module/provider_verifiers.py`
- `shared_lib/shared_module/identity_linking.py`
- `shared_lib/shared_module/portal_data/mobile_repository.py`
- `apps/mobile_api/.env_example.yaml`
- `apps/mobile_api/README.md`
- `apps/mobile_api/apple_verifier.py`
- `apps/mobile_api/app.py`
- `apps/mobile_api/bootstrap.py`
- `apps/mobile_api/openapi.json`
- `apps/mobile_api/tests/test_app.py`
- `apps/mobile_api/tests/test_apple_verifier.py`
- `apps/mobile_api/tests/test_apple_identity_linking.py`
- `apps/mobile_api/tests/test_openapi_contract.py`
- `docs/coordination/reports/TASK-171-MOBILE-AUTH.md`
