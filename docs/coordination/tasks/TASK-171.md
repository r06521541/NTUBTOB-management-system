# TASK-171：Sign in with Apple Repository Vertical Slice

## Task metadata

- type: `delivery`
- delivery_group: `task-171-apple-auth-repository-slice`
- acceptance_level: `L2`（authentication／identity linking；repository-only）
- base: `8ae17853fa24379f6394ff3122c3eccb0be326ec`
- branch: `codex/task-171-apple-auth-repository-slice`
- report_to: `main-work`
- owner_approved: 2026-08-31

## Product decisions and scope

1. iOS public release adopts Sign in with Apple under DEC-103. This task implements the repository client/server/auth contract while Google Play verification keeps TASK-170's external phase waiting.
2. Apple identity uses the stable provider subject as the sole identity key. Email, private relay email, name and real-user status are non-authoritative profile hints and must never auto-merge a Person.
3. Native authorization must be nonce-bound. The Mobile API verifies signature, key metadata, issuer, exact audience, expiry and nonce before the existing server-owned session and identity-link flows may consume the subject.
4. Existing LINE／Google recovery, explicit self-link confirmation, conflict behavior, refresh/logout, installation isolation and offline read-only invariants remain unchanged.
5. Repository implementation may include an unbound iOS capability/source contract and deterministic adapters, but does not enable an Apple Developer App ID, create keys, read identifiers, bind entitlements to a real profile, deploy, or perform a provider smoke.

## Parallel writer claims

### Mobile Auth writer

- actor_id: `/root/task170_play_evidence_writer`
- role: `codex-writer`
- claim_id: `task-171-mobile-apple-auth-writer-20260831`
- lease_version: 1
- scope: Apple assertion verification, Mobile API exchange/link routes, repository candidate behavior, OpenAPI and direct tests
- owned_paths:
  - `shared_lib/shared_module/provider_verifiers.py`
  - `shared_lib/shared_module/identity_linking.py`
  - `shared_lib/shared_module/portal_data/mobile_repository.py`
  - `apps/mobile_api/**`
  - `docs/coordination/reports/TASK-171-MOBILE-AUTH.md`

### Flutter／iOS writer

- actor_id: `/root/task170_android_candidate_writer`
- role: `codex-writer`
- claim_id: `task-171-flutter-apple-auth-writer-20260831`
- lease_version: 1
- scope: dependency-free native iOS authorization bridge, Flutter Apple login/link UX, configuration and deterministic tests
- owned_paths:
  - `clients/flutter_app/lib/**`
  - `clients/flutter_app/test/**`
  - `clients/flutter_app/ios/**`
  - `clients/flutter_app/README.md`
  - `docs/coordination/reports/TASK-171-FLUTTER-IOS.md`

Writers may edit only owned paths. Each must acknowledge `received/executing`, self-review and self-test, send a heartbeat at least every 10–15 minutes, report blockers immediately, and proactively notify Main on completion with exact paths, full SHA if committed, tests, findings, remaining limits and task name. Writers may not access Apple／Google／LINE accounts, provider identifiers, signing material, Secret, cloud, production, deployment or real user data.

## Required outcomes

1. An Apple ID-token verifier uses a bounded cached JWK transport and rejects unknown algorithms／keys, malformed or oversized responses, wrong issuer/audience/nonce, expiry and transport failure without disclosing the assertion or claims.
2. `/auth/apple/exchange` and Apple identity-link candidate/proof routes reuse existing session, explicit confirmation, replay/idempotency and conflict contracts. Email/name are not accepted as identity-link inputs.
3. Flutter exposes Apple login only on supported iOS real composition; development fake and unsupported platforms remain deterministic and network-free. Cancellation, unavailable, timeout/recoverable failure, pending review and successful session paths are covered.
4. iOS native code uses AuthenticationServices, hashes a one-time raw nonce for the provider request, returns only the identity token needed by the server contract, and never persists provider credentials or profile hints.
5. The App Store release marker remains fail closed until this task's repository implementation, independent review and tests are accepted; external entitlement/provider/signing/runtime gates remain explicitly incomplete.

## Verification budget

- Writers: affected complete Mobile API/shared auth suites or Flutter auth/link/iOS validator suites for owned paths.
- Main: targeted cross-provider regression, complete Flutter analyze/test, Python compile/import and diff/scope review.
- One independent Auth/Security targeted reviewer on an immutable integrated commit.
- One ready PR and change-selected hosted CI; merge only when review accepts, required checks are green and PR is conflict-free.

## Stop conditions

- Schema/migration, account migration/transfer or automatic email-based identity merge is required.
- Need for real Apple identifiers, key, client secret, account login/MFA, entitlement/profile mutation, Secret, cloud, provider, production, deployment or real-device sign-in.
- Existing LINE／Google behavior must be weakened, assertion/claim material would enter output, or a safe nonce/signature/audience contract cannot be made fail closed.

## External follow-up after repository merge

Apple Developer capability, exact audience/App ID, signed entitlement/archive inspection, provider configuration, authorization-code validation, Apple refresh-token and revocation／credential-state lifecycle, Secret/runtime binding, macOS/Xcode evidence, real-device smoke and TestFlight remain separate Owner-gated work. TASK-170 remains externally waiting for Google Play developer-account verification and is not superseded by this task.
