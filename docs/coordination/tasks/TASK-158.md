# TASK-158 Event／Activity 唯讀垂直切片

## Classification

- task_type: delivery
- risk: L3 API／authorization／shared boundary
- delivery_group: `event-activity-read-v1`
- requires_independent_pr: true
- authority_branch: `codex/task-158-event-read-slice`
- repository_authority: `8758b6b559f092b9c4c46cf4edff2aa6e925995e`
- production_or_real_data: prohibited

## Active writer claim

- role: `codex-writer`
- claim_id: `task158-event-read-slice-writer`
- lease_version: 1
- actor_id: `/root/event_read_slice_discovery`
- scope: repository-only Event／Activity principal-scoped read delivery
- owned paths: Mobile API／shared Event read implementation and direct tests,
  `docs/coordination/tasks/TASK-158.md`, this task's single writer report;
  delegated Flutter paths are limited to `clients/flutter_app/lib/integration.dart`,
  `clients/flutter_app/lib/basic_app.dart` and their two direct tests
- write: exact task worktree and owned paths only; commit/push authorized, no PR
- report_to: `main-work`
- stop_conditions: schema/migration need, ambiguous authorization, runtime/cloud/Secret,
  notification or attendance mutation, unexpected dirty-state overlap

## Product outcome

讓已登入的 Flutter 使用者查看自己受邀的正式 Event 與有序 Activity
行程，不再只依賴 Web demo。Mobile API 以發布時固定的
`event_invitees` snapshot 作唯一 read authorization，不以目前 qualification
重新推導資格。

## Scope

- Mobile API 新增 `events:read` capability、`GET /events` 與
  `GET /events/{event_id}`。
- 只投影 active Person 在 `event_invitees` 中 `included=true` 的
  `published`／`cancelled`、尚未結束的 Event。
- Event 欄位限 opaque id、title、type、status、start/end 與 ordered
  Activity；Activity 限 opaque id、title、type、position、start/end。
- Activity linked Game 只有同一 principal 依既有 Game scope 可讀時才回傳
  opaque Game id。
- Flutter 提供 production-shaped Event list/detail/timeline、empty/loading/error、
  cancelled 與明確 offline-unavailable 狀態；不修改 cache schema。

## Invariants and non-goals

- draft、excluded invitee、inactive Person 一律 fail closed。
- 不暴露其他 invitee、eligibility、manager、audit、override reason、identity、
  contact 或其他 PII。
- 不修改 schema/migration，不建立／編輯／發布／取消 Event，不新增 Event／
  Activity attendance mutation，不發通知。
- 不部署、不讀寫 cloud／Secret／IAM／production；Event table runtime grants
  仍是後續部署 gate。

## Verification budget

- repository authorization/read-model focused tests
- shared Mobile API service tests
- Mobile API route and OpenAPI contract tests
- Flutter model/widget focused tests、formatter、analyze
- `git diff --check`、scope/status review
- hosted PostgreSQL 15/16、Mobile API、Flutter gates 由 final PR 執行
