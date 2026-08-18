# TASK-112：Isolated mobile staging readiness and operator package

task_type: delivery
delivery_group: mobile-staging-readiness
requires_independent_pr: true
status: ready_for_codex
base_commit: 2c33b6e48f89f43a34f44784e9c224971b5cca38

## Goal

Produce the fail-closed, reviewable operator package required to activate the
mobile API and build a real-config Android staging client later. This task ends
at an exact Owner approval checkpoint: it performs read-only inventory and
offline/local rehearsal only, and does not create, migrate or deploy any cloud,
database, Secret or LINE resource.

## Confirmed inventory and architecture boundary

- Production/default GCP project is `ntubtob-schedule-405614`; repository region
  is `asia-east1`. Read-only inventory on 2026-08-19 found no existing mobile API
  or staging Cloud Run service.
- Staging must use a dedicated GCP project and a dedicated PostgreSQL database;
  tooling must reject the production project and must not accept the production
  database as an override. Final project/database provider, IDs, billing and
  resource creation remain Owner decisions after the package exposes exact
  cost-bearing targets.
- Proposed Cloud Run service name is `mobile-api-staging`, region
  `asia-east1`, min instances 0 and bounded max instances. It will eventually
  require public HTTPS ingress because a native app cannot use Cloud Run IAM,
  while every non-health API route remains protected by app bearer auth and the
  exact revision-0005 gate. Public IAM is not authorized by this task.
- Staging uses revision `0005_mobile_auth_api_foundation`, fictional people,
  games and attendance, and exactly one bounded real tester identity mapping.
  No production row or dataset is copied.

## LINE staging boundary

- Use a LINE Login channel in `Developing` state under the same LINE Provider as
  the existing related Messaging API/Login channels. LINE user IDs differ by
  Provider and channels cannot later move between Providers.
- Enable Mobile app and register Android package `tw.org.ntubtob.portal`.
  Register iOS bundle `tw.org.ntubtob.portal` for later macOS work, but iOS
  runtime acceptance remains deferred.
- Channel ID/audience is non-secret build/runtime configuration. Channel secret
  is not needed by the current ID-token verification contract and must not be
  copied into the client or repository.
- The Owner's real provider subject is private personal data. The operator must
  accept it only from a task-private input at execution time, never print it,
  hash it for diagnostics, or commit it. The staging seed links it to one
  fictional active Person solely for end-to-end login testing.

## Required operator package

### Read-only preflight

- Resolve exact gcloud executable/account/project/region and fail unless the
  target is an explicit non-production project.
- Inventory target Cloud Run/service-account/build/API state and only Secret
  metadata names/versions/IAM references, never payloads.
- Validate a private staging database target by expected host/database identity,
  clean or exact repository-owned fixture state, revision and zero production
  fingerprint. Discovery must be transaction read-only.
- Render a redacted manifest containing target project/region/service, image
  commit/digest placeholder, database identity hash, required Secret references,
  IAM/ingress, scaling, test cohort count and rollback/cleanup actions.

### Local rehearsal and data bootstrap

- Reuse existing legacy setup plus Alembic migrations through 0005; do not add
  or change schema/model/controlled SQL.
- Add a deterministic fictional staging seed with multiple future games and
  attendance states sufficient for the Basic Flutter flow. No notification
  endpoint is configured and no external message is sent.
- Add a private one-tester identity-link step with exact cardinality,
  transaction, post-check and retry-safe behavior. Its input and output must not
  reveal the provider subject.
- Rehearse migration/seed/auth prerequisites on isolated PostgreSQL 15 and 16,
  including rollback/cleanup to the pre-rehearsal local state.

### Build/deployment preparation

- Package the exact current shared library artifact into the mobile API build
  context with secret-safe `.dockerignore` checks.
- Add a mobile-staging deployment operator modeled on the repository's existing
  fail-closed deployment tooling: full commit SHA, exact image digest, pinned
  candidate revision, revision readiness, secret reference contract,
  no-traffic candidate validation, explicit promotion and rollback/cleanup.
- The operator defaults to dry-run/read-only and requires a separate exact
  execution approval artifact. It must never create a project, billing link,
  database, Secret value, service account, IAM binding or LINE channel.
- Define required runtime names without values:
  `PORTAL_DATA_DATABASE_URL`, `MOBILE_API_AUDIENCE`,
  `MOBILE_ACCESS_SIGNING_KEY`, and `MOBILE_REFRESH_REPLAY_KEY`.
- Define the Flutter staging build command using explicit HTTPS API base URL and
  numeric LINE channel ID. Do not build with real values in this task and do not
  upload/distribute an APK.

## Writer boundary

The Shared/Web Codex is the single primary writer in an independent worktree.
It may modify only:

- `apps/mobile_api/**` deployment/readiness files and tests
- new `tools/mobile_staging_*.py`
- matching new/updated `tools/tests/test_mobile_staging_*.py`
- one concise `docs/operations/mobile/MOBILE_STAGING.md`
- `docs/coordination/reports/TASK-112-CODEX.md`

It must not modify migrations, models, shared application behavior, Flutter
source, existing production deployment operators, Makefiles, global
coordination files or any Secret/env payload. Flutter Domain Work may perform a
read-only review of the generated Flutter command and LINE platform boundary;
it is not a second writer.

## Verification

- Offline unit/contract tests for production-project/DB rejection, redaction,
  exact Secret-reference names, dry-run default, candidate/promotion/rollback,
  interrupted-state recovery and private tester cardinality.
- PostgreSQL 15/16 local rehearsal from repository legacy baseline through 0005,
  fictional seed, one fake provider subject and cleanup; no external database.
- Mobile API full offline suite, deployment tool tests, affected compile,
  Black/isort, Docker/build-context static review and `git diff --check`.
- Runbook tabletop proves discovery -> Owner exact approval -> execution ->
  post-check, and lists every expected external mutation and cleanup cost.

## Exact Owner checkpoint after this task

Before TASK-113 may execute anything, Main Work must present and Owner must
explicitly approve:

1. Dedicated staging GCP project ID, billing account linkage and enabled APIs.
2. Dedicated staging PostgreSQL provider/project/host/database and expected
   monthly/free-tier impact.
3. LINE Provider/channel ID and Developing-role tester setup, supplied without
   channel secret or provider-subject disclosure.
4. Secret resource names/versions, dedicated service account, IAM, public
   ingress, scaling and exact Cloud Run service/revision target.
5. One private tester bootstrap mechanism, migration/seed counts, artifact SHA,
   smoke steps, rollback and full staging cleanup plan.

## Not authorized

No GCP project/API/service account/Cloud Run/Cloud Build/IAM/Secret creation or
change; no external DB connection/migration/seed; no LINE Console/channel
change; no real identity read/write; no real API/login/notification; no APK
distribution, signing, TestFlight, store or production operation.

## Execution checkpoint

1. Goal: deliver a fail-closed staging operator package and exact approval
   manifest, not activate staging.
2. Core files: mobile API deployment/readiness files, new staging tools/tests,
   one runbook and one report.
3. Invariants: dedicated non-production project/DB, no Secret/PII output, 0005
   exact, fictional data, dry-run default and explicit promotion/rollback.
4. Tests: offline contracts, PG15/16 rehearsal, mobile API suite, formatting,
   build-context and diff checks.
5. Blockers: project/billing/DB provider/LINE Console/Secret/IAM decisions stay
   at the Owner checkpoint; no external mutation occurs in this task.
