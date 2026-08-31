# TASK-173：Active Authority and Documentation Lifecycle Hardening

## Task metadata

- type: `delivery`
- delivery_group: `task-173-governance-lifecycle`
- acceptance_level: `L2`（repository authority／coordination safety）
- base: `07fed38243883b95ef4c8371566b6859d9f57b31`
- branch: `codex/task-173-governance-lifecycle`
- report_to: `main-work`
- owner_approved: 2026-08-31

## Scope and decisions

1. Replace repeated task-local assignment prose with one mandatory generic packet: exact actor／claim／lease／scope／owned paths, immediate `received/executing`, 10–15 minute heartbeat, immediate blocker, and proactive completion notification to Main with SHA／dirty paths／tests／findings／limits／external mutations.
2. Make the singleton invariant explicit: when `active_task: null`, `task`, `report` and `review` are also null, status is completed and next actor is Owner. Cross-session messages remain transport, never authority.
3. Define repository-owned Owner interaction wrappers: read-only preflight before mutation, hidden sensitive input with visible length-only feedback, ASCII-safe prompts/errors, exact one-shot approval, safe retry classification and no duplicate off-repository evidence. Off-repository helpers cannot become durable authority.
4. Consolidate current-state documents instead of appending: bring `COLLABORATION.md` back within its budget, clarify the superseded DEC-086 wording through existing DEC-101／102, and reduce `PROJECT_STATE.md` to current capabilities, external gates and active lanes.
5. Perform evidence-based Phase D retention. Archive only task/report/review groups whose completion is proved by current repository state or merged Git evidence. Keep TASK-169／170 active because mobile-store readiness and Google Play external verification remain current. Any ambiguous group stays active.

## Claims

### Governance writer

- actor_id: `/root/task170_android_candidate_writer`
- role: `codex-writer`
- claim_id: `task-173-governance-writer-20260831`
- lease_version: 1
- scope: active rules, current-state compaction, safe Phase D retention and focused consistency checks
- owned_paths:
  - `AGENTS.md`
  - `docs/coordination/COLLABORATION.md`
  - `docs/coordination/CODEX_SESSION_ANCHOR.md`
  - `docs/coordination/DECISIONS.md`
  - `docs/coordination/PROJECT_STATE.md`
  - `docs/coordination/HANDOFF.yaml`
  - `docs/coordination/tasks/**`
  - `docs/coordination/reports/**`
  - `docs/coordination/reviews/**`
  - `docs/coordination/archive/phase-d/**`

### Governance reviewer

- actor_id: `/root/task170_release_security_review`
- role: `advisor`
- claim_id: `task-173-governance-reviewer-20260831`
- lease_version: 1
- scope: read-only immutable-SHA review of authority precedence, assignment protocol, null invariant, Owner interaction safety, retention completeness and current external gates
- owned_paths: none

Every assignment follows the generic protocol being established by this task now: ACK `received/executing`, heartbeat after 10–15 minutes, immediate blocker, and proactive final notification. The writer may not commit, push or create a PR; Main integrates and the independent reviewer accepts immutable Git blobs.

## Required outcomes

1. A newly assigned session can determine who acts, what it owns and how it must report without copying task-specific prose.
2. Completed singleton state cannot point to a stale task/report/review.
3. Repository rules distinguish durable reviewed tools from temporary UI helpers and prevent silent, repeated or disclosure-prone Owner operations.
4. Active authority is compact and internally consistent; current product/store/provider gates remain visible after archival.
5. No active or externally pending work is archived, and no archive document is used to grant current authority.

## Verification budget

- Writer: active-reference/claim consistency, document budgets, retention source/destination completeness, link/reference scan excluding archive content, and `git diff --check`.
- Main: exact move audit, current product/external-gate preservation, and no semantic authority expansion.
- One independent Governance／Security review on immutable Git blobs.
- One docs/quick-only hosted gate; merge only if green and conflict-free.

## Stop conditions

- A candidate task/report/review has ambiguous completion or an unresolved external gate.
- Archival would require reading unreferenced archive history or rewriting historical content.
- A rule would authorize production, Secret, provider, store, database, deploy or runtime mutation.
- Necessary safety meaning cannot fit within the documentation budget without deleting an active invariant.

## Non-goals

No product code, test behavior, schema, database, provider, Secret, cloud, store, deployment, runtime or production operation. No archive-history investigation and no new product decision.
