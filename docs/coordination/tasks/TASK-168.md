# TASK-168：Event／Activity 兩層出席回覆 vertical slice

## Task metadata

- type: `delivery`
- delivery_group: `task-168-event-attendance`
- acceptance_level: `L3`（shared persistence/API boundary；本 task 不含 schema rollout 或 deployment）
- base: `10d7cee44b6bd6ff2edb456518a129ebb3692443`
- branch: `codex/task-168-event-attendance-vertical-slice`
- report_to: `main-work`
- status: `completed`
- merged_pr: `#217`
- merge_commit: `cabdbcd039c9d526adb21fd8b11e145cd48f2574`

## Completed writer claim

- actor_id: `/root/task168_event_attendance_writer`
- role: `codex-writer`
- claim_id: `task-168-event-attendance-writer-20260830`
- lease_version: 3
- scope: repository-only Event／Activity attendance persistence、Mobile API、Web Portal、Flutter與直接測試
- owned_paths:
  - `shared_lib/shared_module/portal_data/repository.py`
  - `shared_lib/shared_module/portal_data/identity_lifecycle.py`
  - `shared_lib/shared_module/event_read.py`
  - `shared_lib/shared_module/mobile_api.py`
  - direct shared／portal-data attendance tests
  - `apps/mobile_api/app.py`, `apps/mobile_api/bootstrap.py`, `apps/mobile_api/openapi.json` and direct tests
  - `apps/web_portal/app.py`, Event templates/styles/scripts and direct tests
  - `clients/flutter_app/lib/basic_app.dart`, `clients/flutter_app/lib/integration.dart`, `clients/flutter_app/lib/production_demo.dart` and direct tests including `clients/flutter_app/test/production_demo_test.dart`
  - `docs/coordination/reports/TASK-168-CODEX.md`
- write: exact branch and owned paths only；writer可commit／push handoff，Main負責acceptance、PR、CI與merge
- stop_conditions: schema／migration need、既有Game attendance必須被重寫或雙寫、idempotency無法沿用durable boundary、通知／provider／Secret／cloud／production need、或unexpected dirty overlap

## Product outcome

讓 immutable invitee snapshot 中的 active Person，在同一個正式 Event 詳情中完成整體活動、一般 Activity 與 linked Game 的出席回覆；一般活動使用三態，既有比賽維持五態且只有一個真實來源。

## Required behavior

1. Event 與非 linked-Game Activity 使用既有三態 `attending`／`not_attending`／`maybe`；只有 `published`、未結束、未取消 Event 的 active included invitee 可以讀寫自己的回覆。
2. Event 回覆可明確選擇「套用全部一般行程」，由 server 單一 transaction 更新 Event 與所有非 linked-Game Activity；不得覆寫 linked Game，也不得暗改先前個別 Activity 回覆，除非使用者本次明確選擇套用。
3. linked Game Activity 在相同 Event 畫面重用既有 Game 五態 attendance 元件與 server-owned mutation；不得寫入 `activity_attendance_replies`、不得將三態自動映射為五態、不得建立第二份 Game 回覆。
4. Mobile API mutation 使用既有 durable idempotency contract；Web 使用 session-bound CSRF、canonical route key、Post/Redirect/Get 與站內確認。離線、不確定結果與重送不得誤顯示成功。
5. Web Portal、Mobile API／OpenAPI 與 Flutter 使用一致 public projection；Flutter fake fixtures同步涵蓋整體套用、個別調整、linked Game與失敗狀態。
6. Officer／Admin 可查看低敏感度 Event／Activity 回覆計數與未回覆數；不得暴露 provider identity、contact、override reason、audit或不必要PII。
7. 發布、回覆與通知維持分離；本 task 不發 LINE／Discord／push，不新增 notification／outbox副作用，也不改既有 Game notification語意。

## Persistence and rollback

- 沿用現有 `event_attendance_replies`、`activity_attendance_replies` 與既有 Game attendance；預期不新增 migration。
- 所有 authorization 與 linked-Game exclusion 在 write transaction 內重驗，UI 隱藏不取代 server enforcement。
- Rollback 為停止新 Event／Activity mutation並回到既有 read-only surface；保留已提交的出席資料，不以刪表或清資料回復。
- 若現有 schema／idempotency無法安全支援原子更新，writer停止並交回 Main，不自行新增 `0010`。

## Verification budget

1. Writer：repository in-memory／PostgreSQL direct contracts、Mobile API complete affected suite、Web Portal complete suite、Flutter focused + analyze／format、compile、`git diff --check`。
2. 初版 diff 後由一位具名 Data／Authorization targeted reviewer檢查 snapshot authorization、transaction、idempotency、linked-Game single-source與privacy。
3. Main：實際 diff／scope與少量高價值 regression。
4. Acceptance後建立唯一 ready PR，跑一次 change-selected hosted gate；不使用 emulator、provider、cloud、production DB或deployment。

## Owner-approved product decision

- 2026-08-30：Event／一般 Activity 保留三態；linked Game 保留既有五態。套用全部排除 linked Game，兩種回覆可在同一 Event 畫面完成，但不得互相覆寫或重複儲存。

## Claim revisions

- Lease 2：初始唯讀盤點確認 canonical Event persistence、Mobile service/idempotency 與 Flutter transport/model 分別位於 `identity_lifecycle.py`、`mobile_api.py` 與 `integration.dart`；將這些既有 service-boundary 檔案及 direct tests 納入 owned paths，避免 route／widget 直接繞過 application service。產品範圍、schema與外部操作邊界不變。
- Lease 3：獨立 Data／Authorization review 指出 production-shaped Flutter fake 尚未提供 TASK-168 Event capability、deterministic fixtures與stateful success/failure scenarios；將 `production_demo.dart`、其直接測試及必要相鄰 fake-mode test納入 correction scope。只補 reviewer 唯一 finding，不擴張 production/runtime/schema邊界。

## Completion

- Implementation commit `d7d1fbc9755e1aa66d26b47ff46ea475368ae063` received independent Data／Authorization `ACCEPT` with no remaining actionable findings.
- PR #217 passed every selected hosted gate, including Flutter and PostgreSQL 15／16, and merged as `cabdbcd039c9d526adb21fd8b11e145cd48f2574`.
- Writer lease 3 is complete. Deployment, production data, schema, notification, provider, Secret and cloud operations remain outside this task.
