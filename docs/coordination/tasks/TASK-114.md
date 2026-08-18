# TASK-114：Mobile Officer read-only operational parity

task_type: delivery
delivery_group: mobile-officer-readonly-parity
requires_independent_pr: true
status: ready_for_domain_planning
base_commit: 7ef79b1380ac054b867bcac0fd4b2c317b81d778

## Goal

Deliver a schema-neutral, read-only Officer experience across the mobile API and
Flutter client: server-derived capabilities, scoped single-game attendance
reports and the existing high-frequency non-responder insight. Basic users must
remain isolated. This task does not activate staging or send notifications.

## Product boundary

- Fresh active Person principal remains the authority. Persisted `officer` may
  receive only the explicitly listed read capabilities. `admin` inherits those
  reads, but this task adds no Admin mutation or production allowlist bypass.
- Basic users keep the current games/detail/own reply surface and must not infer,
  enumerate or receive non-responder data.
- The report reuses the repository's bounded observable-game history and
  transparent thresholds. It must distinguish replied and not-yet-replied
  cohorts without inventing roster snapshots or historical eligibility.
- Existing Web behavior and TASK-106 attendance mutation/notification semantics
  must not regress. No notification inbox, push, broadcast or send endpoint is
  added.

## Delivery slices

### A. Shared application/read model and mobile API

- Define server-owned mobile capabilities for Basic and bounded Officer reads.
- Add a scoped Officer/Admin attendance-report application service and route to
  the canonical OpenAPI contract, using Person-based authorization and exact
  visible Game checks before any report data is returned.
- Return low-sensitive DTOs, stable ordering, honest observation-window counts,
  bounded thresholds and standard error envelopes. Unauthorized/not-visible
  resources fail closed without existence leakage.
- Keep revision exactly `0005_mobile_auth_api_foundation`; no migration, model,
  controlled SQL or new durable state.

### B. Flutter real read-only integration

- Map `/me` capabilities to role-neutral client policy; never trust a locally
  selected fictional persona in real mode.
- Connect the existing management hub to real single-game attendance reports.
- Provide loading, empty, retryable error, forbidden/session-expired and cached
  offline read-only states. Offline data is isolated by principal and cannot
  enable mutation.
- Basic navigation stays at four destinations and cannot discover management
  routes. Officer/Admin remain at no more than five bottom destinations.
- Keep notification, broadcast, push and Admin mutation surfaces visibly
  fictional/disabled or absent in real mode.

### C. Contract and integration verification

- Update canonical OpenAPI and checked fixtures in lockstep with runtime DTOs.
- Cover Basic/Officer/Admin capability matrices, fresh-principal downgrade,
  inactive/unlinked identities, invisible/cancelled/missing Games, empty/error
  reports, stable sorting, privacy projection and no mutation/notification.
- Run Python 3.10 mobile API/shared tests, PostgreSQL 15/16 only if affected
  repository SQL requires them, Flutter format/analyze/tests/fake debug build,
  classifier/final-gate contracts and `git diff --check`.

## Writer lanes

- Shared/Web Codex is the sole writer for `shared_lib/**`, `apps/mobile_api/**`,
  canonical mobile contract/tests and its single TASK-114 report.
- Flutter Domain Work owns Flutter scope/review. Its sole Flutter Codex writer
  works in a separate worktree/branch and may modify only
  `clients/flutter_app/**` plus its single TASK-114 Flutter report.
- The two lanes must not edit the same file. Main Work owns task/global
  coordination, final integration, PR and merge.

## Invariants

- No schema revision, migration, model or production role/allowlist change.
- No deploy, staging activation, Secret/IAM/LINE Console operation, database
  mutation, real login, notification, push, broadcast or external message.
- No Officer/Admin write endpoint. Attendance reply remains the existing
  self-only TASK-106 mutation and is not expanded by this task.
- Any missing wire field or authorization ambiguity is escalated to Main Work;
  neither lane invents a cross-domain contract independently.

## Completion

One final PR after both lanes are accepted and integrated. Hosted CI must prove
the existing final gate. Real staging/device/LINE smoke remains TASK-113 and
requires separate exact Owner approvals.

## Execution checkpoint

1. Goal: mobile Officer read-only attendance-report parity, not notification or staging activation.
2. Core files: shared read service, mobile API/OpenAPI, Flutter integration and bounded tests.
3. Invariants: revision 0005, fresh principal, Basic isolation, zero new mutation/external side effect.
4. Tests: capability/privacy matrices, route/contracts, Flutter states/navigation, hosted final gate.
5. Blockers: none for repository-only implementation; ambiguous role or DTO semantics fail closed and return to Main Work.
