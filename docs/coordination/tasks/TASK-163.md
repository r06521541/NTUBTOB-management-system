# TASK-163 Event／Activity 管理寫入垂直切片

## Classification

- task_type: delivery
- risk: L3 schema／authorization／shared transaction boundary
- delivery_group: `event-activity-management-v1`
- requires_independent_pr: true
- authority_branch: `codex/task-163-event-management-write-v1`
- repository_authority: `4d4b3502451544f5b9efeb9c2bfd4c605d6385a2`
- production_or_real_data: prohibited

## Active writer claim

- role: `codex-writer`
- claim_id: `task-163-event-management-write-writer-20260827`
- lease_version: 1
- actor_id: `/root/task160_web_portal_writer`
- state: `active`
- scope: repository-only Event／Activity management contract, persistence and Web Portal delivery
- owned paths:
  - `migrations/versions/0009_event_management_writes.py`
  - `shared_lib/shared_module/portal_data/models.py`
  - `shared_lib/shared_module/portal_data/repository.py`
  - `shared_lib/shared_module/portal_data/services.py`
  - direct repository／migration tests under `tests/portal_data/`
  - `apps/web_portal/app.py`
  - Event management templates／styles／scripts and direct Web Portal tests
  - `docs/coordination/tasks/TASK-163.md`
  - `docs/coordination/reports/TASK-163-CODEX.md`
- write: exact task branch and owned paths only; commit/push handoff authorized; Main owns acceptance, PR, merge and any later deployment
- report_to: `main-work`
- stop_conditions: existing schema cannot support additive rollback-safe migration, ambiguous Person/capability mapping, notification coupling, production/runtime/cloud/Secret/IAM need, real-data access, or unexpected dirty overlap

## Product outcome

讓 active Officer／Admin 在 Web Portal 建立與管理正式 Event 草稿、編排行程、預覽資格池與發布固定邀請快照；發布後既有 Web／Flutter read surfaces 可直接讀取同一份 Event。發布不發通知，也不改既有 Game／crawler ownership。

## Required behavior

1. Active Officer／Admin 可建立 Event 草稿、編輯基本資料及新增／編輯／刪除／排序 Activity；basic、inactive、principal mismatch 與未知角色一律在任何資料 mutation 前拒絕。
2. 草稿必須選至少一種 qualification eligibility。管理畫面提供去識別化的資格池預覽與人工 include／exclude override；override 必填 3–300 字理由。
3. 發布由單一明確確認 POST 完成，不要求第二位幹部。Repository 以單一 transaction 鎖定 Event、重驗 actor、產生 immutable `event_invitees` snapshot、append audit 並切換為 published；相同 request id／已發布重送不得重複 snapshot 或 audit。
4. Published Event 可修改標題、類型、起訖與 Activity itinerary，但不得重新計算或暗改 invitee snapshot；所有 published edit 必須 append audit。Published Event 可明確取消且保留 snapshot；取消不可自動通知。
5. Event 與 Activity 時間使用 timezone-aware Asia/Taipei 輸入／顯示與 UTC persistence。Activity 必須隸屬同一 Event、position 唯一且連續；linked Game 本輪只保留既有 read contract，不新增 crawler、去重或 manual Game 寫入。
6. 所有 Web POST 使用 session-bound CSRF、canonical positive bigint route key、server-owned actor、bounded input、Post/Redirect/Get 與站內確認 UI。UI 隱藏不取代 server authorization。
7. 不實作 Event／Activity attendance、guest同行者、notification／outbox、provider、Secret、runtime、deployment或 production data mutation。

## Persistence and rollback

- 優先沿用現有 Event／Activity／eligibility／override／invitee schema；只允許為 edit／cancel audit 與 idempotency 所需的 additive migration。
- Migration 必須由 revision `0008` 可升級，保留舊 revision read safety；rollback 停止新 mutation並保留 Event／snapshot資料，不以 drop Event domain 作緊急 rollback。
- Repository contract需同時涵蓋 in-memory 與 PostgreSQL implementation；Web route不得直接操作 ORM table。

## Verification budget

- Writer 先建立 authorization、validation、idempotency、snapshot immutability、published edit/cancel audit、Activity ownership/order regressions。
- Writer 執行完整 Event repository contract、PostgreSQL 15／16 migration/constraint suite、Web Portal affected-full suite、formatter/compile、`git diff --check`與scope review。
- 初版 diff 後由一名 Data／Authorization reviewer只檢查 transaction、snapshot、audit、CSRF與rollback boundary。
- Main 做 focused contract與Web mutation regressions、diff/scope review；接受後只跑一次 hosted change-selected full gate。
- 本 task merge 不授權 schema rollout、deployment、通知或其他外部 mutation。

