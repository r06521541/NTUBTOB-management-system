# TASK-159 Web Portal Event／Activity 唯讀 parity

## Classification

- task_type: delivery
- risk: L3 authorization／shared boundary
- delivery_group: `event-activity-read-v1`
- requires_independent_pr: true
- authority_branch: `codex/task-159-web-event-read-parity`
- repository_authority: `64b95e61e6fc24a17e99ac9b90207287ec835109`
- production_or_real_data: prohibited

## Active execution claim

- role: `main-work`
- claim_id: `main-work-20260825`
- lease_version: 17
- actor_id: `01a03587-d263-7e92-9965-54816f38b8a3`
- scope: repository-only Web Portal Event／Activity read parity and coordination reconciliation
- owned paths: Web Portal Event routes/templates/styles/tests, shared Event public read contract and direct Mobile regression tests, this task and current coordination singleton/state
- write: exact task branch and owned paths only; commit/push/final PR/green merge authorized
- report_to: `owner`
- stop_conditions: schema/migration need, ambiguous principal mapping, Event mutation, notification, runtime/cloud/Secret/IAM/deploy, production or real-data access, unexpected dirty-state overlap

## Product outcome

讓已登入 Web Portal 的 active Person 查看自己受邀的正式 Event 列表、詳情與有序 Activity timeline，與 Flutter 共用同一個 immutable invitee snapshot read boundary。

## Scope

- 新增 production-shaped `GET /events` 與 `GET /events/event_<id>`。
- route 只接受 canonical positive PostgreSQL bigint opaque Event key。
- Web Portal 直接使用 `IdentityLifecycleRepository.scoped_events/scoped_event`；不另寫可見性查詢。
- 公開 projection 與 Mobile API 共用 server contract，只包含 TASK-158 已核准欄位。
- 呈現 empty、safe unavailable、published、cancelled、ordered timeline 與 scoped linked Game navigation。
- 導覽加入活動入口，維持 desktop／mobile accessibility 與既有 offline demo 隔離。

## Invariants and non-goals

- 只允許 request-time session 與 active lifecycle principal 完全一致的讀取。
- draft、excluded invitee、inactive Person、ended Event 與不可見 linked Game 繼續 fail closed。
- 不暴露 invitee、eligibility、manager、audit、override reason、identity、contact 或其他 PII。
- 不新增 schema/migration，不建立、編輯、發布、取消 Event，不新增 attendance mutation，不發通知。
- 不部署、不讀寫 cloud／Secret／IAM／production；Event table runtime grants 仍是 deployment gate。

## Verification budget

- shared Event contract tests
- IdentityLifecycleRepository Event authorization tests
- Web Portal complete route/UI suite
- Mobile API route/service/OpenAPI regressions
- formatter/import compile、`git diff --check`、scope/status review
- final PR 使用 change-selected hosted full gate，包含 PostgreSQL 15／16
