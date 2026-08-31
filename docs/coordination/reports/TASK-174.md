# TASK-174 implementation report

## Outcome

- iOS native Apple authorization returns only a bounded ID token and single-use
  authorization code. Flutter forwards that exact envelope with the existing
  nonce, attempt, installation, and iOS platform fields.
- Mobile API verifies the first ID token locally, reserves the code hash, performs
  one bounded HTTPS exchange, correlates the returned subject, and persists only
  an independently encrypted refresh credential plus hashes.
- The provider credential cipher is separate from the normal mobile refresh
  successor cipher. Native, Flutter, OpenAPI, and backend ID-token bounds are
  aligned at 16,384 bytes/characters, and the token endpoint accepts only the
  case-insensitive OAuth `bearer` token type.
- Migration `0010_apple_provider_lifecycle` adds bounded one-shot code state,
  encrypted credential state, and notification JTI receipts without destructive
  downgrade behavior.
- A public form endpoint verifies Apple's no-expiry outer JWS shape, bounded
  issued-at/JTI, and Unix-seconds event time before mutation. Consent
  revocation and account deletion atomically disable the Apple identity, mobile
  sessions, and credential; email forwarding events remain receipt-only.
- Apple lifecycle remains disabled unless all runtime configuration and exact
  schema readiness are present. No provider, signing, cloud, Secret, deployment,
  production, or real-device mutation occurred.
- Core readiness accepts only revisions 0008, 0009, and 0010, permitting the
  compatible runtime to deploy before the 0010 migration. At 0008/0009, LINE and
  Google remain usable while Apple exchange and notifications stay unavailable.
- Apple lifecycle configuration also fails closed when its provider-credential
  key reuses the normal mobile refresh replay key; no key value is logged.

## Verification

- `flutter test --no-pub test/apple_auth_test.dart`: 10 passed.
- `flutter analyze --no-pub lib/integration.dart lib/identity_link.dart test/apple_auth_test.dart`:
  no issues.
- `py -3.10 -m unittest discover -s apps/mobile_api/tests -v`: 77 passed.
- `py -3.10 -m unittest discover -s shared_lib/tests -v`: 69 passed.
- `py -3.10 -m unittest discover -s tests/portal_data -v`: 288 run,
  139 passed and 149 expected isolated-PostgreSQL skips.
- `py -3.10 -m compileall -q shared_lib/shared_module apps/mobile_api migrations/versions tests/portal_data`:
  passed.
- `py -3.10 setup.py sdist` from `shared_lib/`: passed.
- Pinned Black 24.4.2 and isort 5.13.2 formatter API comparisons: passed.
  The repository bounded wrapper safely reported Black CLI timeouts on Windows;
  no formatter process remained.

## Remaining acceptance limits

- PostgreSQL 15/16 upgrade/runtime matrix and hosted CI remain required.
- Independent Auth/Security rereview accepted immutable SHA
  `820f5e13a8674a28972dfdb1931f0a6b32515feb` with no remaining finding; its
  focused Python total was 93 passed and Flutter Apple remained 10 passed.
- Mobile API core runtime readiness permits only 0008/0009/0010, while Apple
  lifecycle readiness and the canonical migration head require exact
  `0010_apple_provider_lifecycle`; historical environment-specific staging/event
  rollout contracts remain unchanged.
- Provider capability, client-secret generation/rotation, notification URL,
  credential-state inspection, active provider-token revocation, signing,
  macOS/Xcode archive, TestFlight, deployment, and real-device Apple login remain
  future Owner gates. The public-release repository marker remains fail closed.
