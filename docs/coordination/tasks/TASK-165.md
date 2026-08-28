# TASK-165 Event management authority alignment

## Classification

- task_type: security hotfix delivery
- risk: L2 production authorization boundary
- delivery_group: `event-management-authority-alignment`
- authority_branch: `codex/task-165-event-management-authority-alignment`
- repository_authority: `6b0aa7e556d25cb906bf12f4ea0c7eed57705f13`
- production_or_external_mutation: prohibited

## Active writer claim

- role: `codex-writer`
- claim_id: `task-165-event-management-authority-writer-20260828`
- lease_version: 2
- actor_id: `/root/task160_web_portal_writer`
- state: `completed_pending_review`
- report_to: `main-work`
- scope: Web Portal and shared repository Event-management authority alignment
- owned paths:
  - `apps/web_portal/app.py`
  - direct tests under `apps/web_portal/tests/`
  - `shared_lib/shared_module/portal_data/repository.py`
  - `tests/portal_data/test_repository_contract.py`
  - `docs/coordination/tasks/TASK-165.md`
  - `docs/coordination/reports/TASK-165-CODEX.md`
  - `docs/coordination/HANDOFF.yaml`
  - `docs/coordination/PROJECT_STATE.md`
- write: exact task branch and owned paths only; writer may commit/push handoff, Main owns acceptance and PR
- stop_conditions: DECISION change required, lifecycle/identity consistency cannot remain fail closed, production/cloud/DB/Secret/IAM/notification need, or unexpected dirty overlap

## Required behavior

1. Production `/manage/events` and every descendant route use the request-time `get_current_principal()` plus `MANAGE_EVENTS` capability contract; raw persisted Person access level is not production authority.
2. An allowlisted administrator may manage Events even when persisted access remains `basic`. A non-allowlisted persisted `officer` or `admin` remains denied in production.
3. Local fictional preview keeps persisted `officer` and `admin` Event management behavior.
4. Active Person lifecycle and exact session Person/identity consistency remain mandatory and fail closed before service calls.
5. The management hub computes Event-entry visibility from the same request principal and capability; it must not hard-code access.
6. `PostgresTeamPortalRepository` receives an immutable allowlist of legacy Member IDs and an explicit local-preview persisted-role mode. Its Event write guard requires an active Person and either an exact linked allowlisted Member or the explicit preview fallback.
7. Production Web composition passes the parsed runtime allowlist with persisted-role fallback disabled; local fictional preview explicitly enables that fallback. The global Portal navigation uses the same canonical capability plus active lifecycle gate.

## Verification budget

- Add positive and negative authorization regressions before implementation.
- Run affected authorization/Event tests and the complete supported Web Portal suite.
- Run Python compile, selected formatter checks, `git diff --check`, scope/self-review.
- Do not access a database, cloud/runtime, Secret, IAM, provider, deployment or notification surface.

## Writer result

- All production Event-management routes now require the canonical request principal's `MANAGE_EVENTS` capability; persisted `Person.access_level` is not consulted as production authority.
- The management hub uses that same capability for the Event entry while preserving the existing, separately bounded game-management gate.
- Regressions cover allowlisted persisted-basic access, denial of non-allowlisted persisted officer/admin access, local fictional preview compatibility, inactive/unlinked fail-closed behavior, constructor policy wiring, and hub／global-navigation／route consistency.
- Writer verification evidence is recorded in the task report. Independent Auth／Identity and Data／Auth reviews accepted the corrected boundary; hosted PostgreSQL／Web CI, PR and any deployment remain Main／Owner gates.
