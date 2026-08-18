# TASK-110：Flutter Basic native auth and API integration

task_type: delivery
delivery_group: flutter-basic-api-integration
requires_independent_pr: true
status: ready_for_codex
base_commit: cd28d60d328844f94d9544aa50965cf77cb2399e

## Goal

Replace the fictional transport for the Basic persona with the accepted TASK-109
`/api/v1` contract while preserving the TASK-105 UI boundary. Deliver native
LINE login, durable app-session behavior, real Basic reads, five-state
attendance replies, deterministic cache/offline behavior and an Android debug
build that uses only explicit non-production configuration.

The canonical wire contract is `apps/mobile_api/openapi.json`; explanatory
semantics live in `docs/planning/MOBILE_AUTH_API_CONTRACT.md`. Flutter must not
invent fields, capability rules or backend behavior that are absent there.

## Approved implementation boundary

- Pin the official `flutter_line_sdk` package at exact version `2.7.2` and use
  native LINE Login with `openid`. Send only the raw ID token, the exact nonce
  used for that login attempt and the bounded login-attempt metadata required by
  the canonical API. Provider profile/user ID is never an identity assertion.
- Pin Android `minSdk` to 24 and add the main-manifest `INTERNET` permission
  required by real HTTPS transport. Keep release signing absent. Keep the iOS
  deployment target at 15; source/config review is in scope, while runtime
  evidence remains deferred to macOS/Xcode.
- Development may explicitly select deterministic fake repositories. Staging
  and production composition must require an HTTPS API base URL and LINE
  channel ID at build time and fail closed when either is missing or invalid.
  No real endpoint, channel ID, credential or Secret is committed.
- App access tokens remain memory-only. Refresh tokens use platform secure
  storage with installation isolation, Android backup/restore exclusion and an
  reviewed iOS Keychain accessibility choice. Unknown or terminal session state
  fails closed.
- Implement single-flight refresh, one-request replay after refresh,
  refresh-attempt replay, logout-pending recovery and offline read-only state.
  Backend current-device revocation is authoritative. Full logout also attempts
  local LINE SDK logout; provider cleanup failure must not recreate an app
  session or claim backend revocation failed.
- Integrate Basic-only `me`, paged games, game detail, own/team attendance and
  five-state attendance mutation. Use one idempotency key per confirmed logical
  mutation; uncertain results reconcile through the authoritative attendance
  read before retrying with the same key.
- Preserve TASK-105 widgets, themes, capability policy and fake fixtures for
  development/tests. Production-shaped composition must not expose fictional
  Officer/Admin capabilities. Notification, push and deep-link payload
  integration remain visibly unavailable/deferred rather than backed by an
  invented endpoint.

## Required states and privacy rules

- Auth UI distinguishes booting, logged out, provider active, exchanging,
  cancelled/recoverable failure, identity pending, account unavailable,
  session expired, logout pending, authenticated and offline read-only.
- Stale/duplicate callback, missing/unknown flavor or config, nonce mismatch,
  timeout, unsupported platform and malformed contract fail closed.
- Basic attendance shows only the caller's reply and people returned in the
  server's `replied` projection. It never infers or displays an unreplied roster.
- Unknown JSON fields are tolerated; missing required fields, unknown enums and
  malformed RFC3339 values fail through typed errors. Raw response bodies,
  tokens, nonce, provider profile and sensitive payload are never logged.
- Offline cache is versioned and partitioned by installation/person. Logout or
  account transition clears person-scoped cached data. Offline mutation never
  looks successful and is not queued by this task.

## Writer and dependency boundary

Flutter Domain Work owns scope review and directs one Flutter Codex writer in an
independent worktree/branch. The implementation writer may modify only:

- `clients/flutter_app/**`
- `docs/coordination/reports/TASK-110-CODEX.md`

Flutter Domain Work may add the single TASK-110 Flutter review and update this
task's status on its shared integration branch. It must not modify root
`HANDOFF.yaml`, `PROJECT_STATE.md`, `DECISIONS.md`, backend/shared code, schema,
OpenAPI or deployment infrastructure. Any discovered API mismatch returns to
Main Work instead of being patched independently in Flutter.

## Verification

- Unit/contract tests for exact OpenAPI DTOs, five reply enums, typed errors,
  unknown fields and required-field failures.
- Session tests for cold start, terminal/transient refresh failures, ten
  concurrent 401s with one refresh, one retry maximum, refresh lost response,
  secure-write failure, logout-pending restart and cache isolation/clearing.
- Native-login adapter tests for nonce/attempt uniqueness, cancel, stale or
  duplicate callback and redaction. Real LINE login is not performed.
- Widget tests for all auth/read states, Basic-only navigation, offline mutation
  disablement and fake-versus-real composition boundaries.
- `flutter pub get`, Dart format check, `flutter analyze`, `flutter test`, and
  Android development debug build using obvious fictional build-time values.
- Static checks for Android minSdk 24, required INTERNET permission, no release
  signing fallback, no tracked build/cache/credential artifacts and no token or
  endpoint leakage.

## Not authorized / deferred

- No backend, OpenAPI, schema or shared-library modification.
- No production migration, deployment, Secret/IAM/cloud change, real LINE
  verification/login, real notification, staging traffic, signing, APK upload,
  TestFlight or store action.
- Officer/Admin real API integration, notification center, push/deep links,
  Google/Apple linking and iOS runtime build remain later work packages.

## Execution checkpoint

1. Goal: connect the existing Flutter Basic shell to the accepted native auth
   and mobile API contract without widening server authority.
2. Core files: `clients/flutter_app/**` and one TASK-110 Codex report.
3. Invariants: exact API contract, fail-closed auth/config, secure refresh
   storage, Basic-only privacy, no production or Secret.
4. Tests: DTO/session/login/widget suites, format/analyze/test and Android debug
   build plus static manifest/signing/artifact checks.
5. Blockers: real staging/channel values and iOS/macOS evidence are intentionally
   deferred; any actual contract mismatch escalates to Main Work.
