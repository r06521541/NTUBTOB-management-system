# TASK-145: Flutter experience and durable notifications

- Task type: delivery umbrella
- Delivery group: `mobile-experience-notifications`
- Risk level: mixed L1/L3; each delivery unit is reviewed independently
- Repository authority: `9cd006cf93c61185c868d5d571230953b4e72b35`
- Owner gate: none for repository work; exact approval remains required for deployment, production/staging data mutation, Secret/IAM, real LINE/Discord/push delivery, release signing and stores

## Goal

Deliver a coherent mobile experience in three dependency-ordered units: establish
the reusable visual system and truthful refresh feedback; add a durable in-app
notification centre; then add server-owned Officer publishing and push/deep-link
seams without making an external notification provider a prerequisite for
durable in-app history.

## Delivery units and ownership

### 145A — Flutter visual foundation and game polish (L1)

- claim_id: `task-145a-flutter-visual-writer`
- lease_version: 1
- actor: one `codex-writer`, assigned by Main
- owned paths:
  - `clients/flutter_app/lib/app_theme.dart` (new)
  - `clients/flutter_app/lib/basic_app.dart`
  - `clients/flutter_app/lib/production_demo.dart`
  - `clients/flutter_app/lib/main.dart` only if theme composition requires it
  - `clients/flutter_app/test/basic_app_test.dart`
  - `clients/flutter_app/test/production_demo_test.dart`
  - `docs/coordination/reports/TASK-145A-FLUTTER-CODEX.md`
- scope: shared brand theme, type/spacing/card/status primitives, home/game-card/detail polish, accessible loading/empty/error/offline states, and refresh feedback that visibly returns the list to its intended position and updates the rendered sync time only after a successful reload.
- invariants: no API/auth/session/cache/capability/attendance behavior change; offline remains read-only with no pull action; production-shaped fake demo reuses production widgets.

### 145B — Durable notification read model and Flutter centre (L3)

- claim_id: `task-145b-notification-read-model-writer`
- lease_version: 1
- actor: one `codex-writer`, assigned by Main
- owned paths:
  - `migrations/versions/0007_mobile_notifications.py` (new)
  - `shared_lib/shared_module/portal_data/models.py`
  - `shared_lib/shared_module/portal_data/mobile_repository.py`
  - `shared_lib/shared_module/mobile_api.py`
  - `apps/mobile_api/app.py`
  - `apps/mobile_api/openapi.json`
  - directly affected backend tests
  - `clients/flutter_app/lib/notification_center.dart` (new)
  - `clients/flutter_app/lib/integration.dart`
  - notification-centre focused Flutter tests
  - `docs/coordination/reports/TASK-145B-NOTIFICATIONS-CODEX.md`
- scope: persistent notification/content/recipient/read-state model; recipient-scoped list/detail/unread-count/mark-read/mark-all-read APIs; 90-day member visibility; principal-scoped Flutter cache and offline read-only presentation.
- invariants: recipient scope is enforced by server-derived Person identity; cursor/order are deterministic; read mutations are idempotent; identity change, logout, terminal session, authorization loss and cache corruption purge/fail closed; notification content and recipient expansion never enter generic logs.

### 145C — Officer publishing, outbox, device registration and deep links (L3)

- claim_id: `task-145c-notification-publishing-writer`
- lease_version: 1
- actor: assigned only after 145B contract is frozen
- owned paths: declared at assignment and must not overlap an active writer
- scope: capability-gated individual/game/team recipient preview; exact preview revision and typed confirmation; at-most-one command via idempotency key; immutable audit and per-channel delivery result/outbox; device registration lifecycle; typed in-app/push destinations for notification detail or game detail.
- invariants: Flutter holds no LINE/Discord/provider secret and never expands recipients; durable notification commit is independent of provider success; provider failure remains a truthful retryable delivery result and cannot erase in-app history; no real provider adapter is enabled, invoked or provisioned in this task; all fictional dispatch tests use rejecting/fake adapters.

## Frozen product contract

- Types: game reminder, attendance reminder, game change, Officer personal,
  Officer game broadcast, Officer team broadcast and Admin system announcement.
- Member-visible notifications are retained for 90 days. Officer/Admin audit is
  append-only and retained independently. Badge counts unread, unexpired rows.
- Plain text only, maximum 500 characters. Publishing is immutable: no edit,
  retract or delete. A preview is not authorization; the server revalidates the
  capability and exact recipient revision during confirmation.
- Officer publishing requires a new exact server capability; role-label checks
  are insufficient. Basic never sees publishing routes or recipient data.
- Deep-link destinations are typed identifiers, never arbitrary URLs. Unknown,
  unauthorized or expired destinations fall back safely to notification list.
- Push is a delivery channel, not the source of truth. App history remains usable
  when token registration or push delivery fails.

## Verification budget

- 145A writer: formatter, analyze and affected Flutter tests. Main performs one
  cumulative UI/invariant review. No Domain reviewer or emulator gate by default.
- 145B writer: migration/model/API affected suites on PostgreSQL 16 plus focused
  Flutter integration/cache tests. Data Domain performs one schema/auth/cache
  review. Hosted CI runs change-selected PostgreSQL 15/16 and Flutter gates once.
- 145C writer: affected service/unit/contract tests with fake/rejecting adapters.
  Domain review is limited to authorization, recipient scope, idempotency/audit,
  delivery separation and deep-link safety. Hosted CI is the final gate.
- Evidence is reusable only for the exact HEAD, command, runtime/DB matrix and
  relevant artifact fingerprint. No unchanged suite is rerun without a new risk.
- Correction budget: one batched correction round per unit. A second unrelated
  issue becomes a follow-up unless it blocks security, data integrity or build.

## Acceptance

- Fake demo visibly demonstrates the refreshed branded game experience and all
  notification states without network, credentials or platform services.
- A signed-in member can list, open and mark only their notifications, see a
  truthful unread count, and read the last successful cache offline.
- An authorized Officer can preview and confirm bounded fictional recipients;
  duplicate confirmation is idempotent and every outcome is auditable.
- In-app notification persistence succeeds independently of push/LINE/Discord;
  provider failure is visible but does not lose history.
- Device/deep-link contracts are typed and tested, but no external push,
  Secret/IAM, deployment, staging mutation or real notification is performed.

## Execution checkpoint

1. Goal: user-visible visual polish followed by a reliable notification centre and safe publishing foundation.
2. Core files: Flutter theme/basic/detail; portal-data migration/models/repository; Mobile API/OpenAPI; notification/push adapters.
3. Key invariants: server authorization and recipient expansion, durable history before delivery, offline read-only cache, no client/provider secrets.
4. Minimum tests: focused Flutter; PostgreSQL migration/repository/API matrix; idempotency/audit/failure tests; one change-selected hosted gate per unit.
5. Blockers: only external provisioning/deployment/real notification/signing or a contract ambiguity that changes recipient authorization.

## Status

- 2026-08-22: planned and authorized for repository implementation.
- Current unit: 145A and 145B contract/implementation may proceed in parallel;
  145C waits for 145B contract freeze.
