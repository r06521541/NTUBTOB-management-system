# TASK-106：Attendance reply application service

task_type: delivery
delivery_group: attendance-reply-service
requires_independent_pr: true

## Goal

Create one server-owned attendance reply application service shared by the Web
Portal and the Phase-C LINE webhook caller. The service owns the existing
`changed` result and urgent-management-notification decision while the
repository remains authoritative for reply validation, future/open Game state,
eligibility, persistence, and same-reply detection.

## In scope

- Add a Python 3.10-compatible shared application module with a typed result,
  injectable clock, and injectable notification port.
- Preserve all five existing attendance reply values (`1..5`) by delegating to
  the repository without duplicating its domain gates.
- Notify only after a changed reply has committed and the request time is
  strictly inside the 12 hours before Game start. Exactly 12 hours before start
  does not notify, matching the existing LINE behavior.
- Make notification best-effort: a notifier failure never rolls back or reports
  an already-saved reply as failed, and only a bounded safe diagnostic/result is
  produced.
- Thin the Web Portal and Phase-C LINE webhook callers while preserving their
  ingress, authentication, session, CSRF, capability, rollout-freeze, and
  response-message contracts.
- Add offline service and direct-caller regression tests, then update the single
  TASK-106 Codex report.

## Out of scope

- Schema, migration, model, controlled SQL, DDL, production DB/data, or
  PostgreSQL matrix changes.
- Legacy LINE attendance persistence redesign, mobile API/auth, Flutter files,
  Event/Activity, outbox/retry schema, or notification delivery redesign.
- Production, deployment, Secret, IAM, Scheduler, cloud resources, external
  HTTP, or real LINE/Discord notifications.
- Global coordination files (`HANDOFF.yaml`, `PROJECT_STATE.md`,
  `DECISIONS.md`, `COLLABORATION.md`) remain owned by Main Work.

## Execution checkpoint

1. Goal: one shared application service for reply persistence outcome and the
   strict 12-hour urgent-notification decision.
2. Core files: new shared module/exports/tests plus direct Web and LINE callers
   and tests; this task and its single report.
3. Invariants: repository gates remain authoritative; notifications happen
   after commit and are best-effort; Web/LINE security gates remain unchanged.
4. Tests: service success, unchanged, outside/exactly-at/inside 12 hours,
   notifier failure, repository failure; Web/LINE regressions and full relevant
   offline suites; compile, Black 24.4.2, isort, diff/status.
5. Blockers: none. No PostgreSQL matrix is required because schema/model/SQL do
   not change.

## Acceptance

- Tests first reproduce the Web notification gap and LINE-owned decision.
- Both Phase-C callers invoke the same service without copying the time/changed
  gate.
- A changed reply outside or exactly at the 12-hour boundary does not notify;
  one strictly inside does. An unchanged reply never notifies.
- Repository failure propagates as a persistence failure. Notification failure
  returns a successful saved result with a bounded failure flag and no secret or
  exception payload.
- Bundled-Python shared, Web Portal, and LINE webhook suites pass, as do affected
  `py_compile`, Black 24.4.2 formatter/check, isort, `git diff --check`, and
  `git status --short`.
