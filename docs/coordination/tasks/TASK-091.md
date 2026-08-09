# TASK-091：Phase D capability policy and smoke preparation

task_type: delivery
delivery_group: phase-d-capability-and-smoke
requires_independent_pr: true
status: ready_for_codex
owner: work
codex: codex

## 目標

落實已確認的 Basic／Officer／Admin capability contract，並提供非 production 一般瀏覽器與 LINE in-app browser
smoke 的可執行準備；不執行 production cutover。

## 範圍

- Basic 可查看低敏 Person 列表，至少包含 access/status 與球員資格摘要；不得顯示電話、醫療、私人備註或完整 provider subject。
- Basic／Officer/Admin 可修改自己的暱稱；Officer 可修改他人基本資料，但不得修改他人暱稱。
- Officer 可處理 pending identity、新增 Member、管理 qualification，以及變更受限的 Person access/status。
- Officer 不得自我升權、指派／移除 admin、移除最後 active admin，或直接執行 blocked recovery；高風險操作維持 admin／二次確認邊界。
- capability policy、route mapping、UI visibility 與 server-side authorization 一致；URL 維持 `/manage/...`。
- 建立 prepare／二次確認／send 分離的通知 capability contract；本 TASK 不實際發送通知。
- 建立非 production browser／LINE in-app browser smoke runbook、測試情境、證據格式與停止條件。

## 非目標

- 不執行 production deployment、allowlist cutover、DB DDL/DML、正式資料 mutation、Secret、IAM、Scheduler 或真實通知。
- 不新增 schema 欄位來補齊目前尚缺的球員資料；缺漏欄位另案規劃。
- 不決定正式通知最終角色核准人；本 TASK 只保留二次確認 contract。
- 不實作 Event domain 或 Google／Apple OAuth。

## 驗收條件

- route 與 domain 都 fail closed；未知 capability／role/status 拒絕，且 side effect 前完成 authorization。
- coverage 包含 Basic／Officer／Admin 的 allow／deny matrix、self-edit、他人編輯、last-admin、self-lockout、blocked recovery、CSRF、audit 與 retry。
- Basic Person list 的欄位符合低敏邊界；Officer 管理操作不得繞過集中 capability policy。
- notification prepare／confirm／send contract 有 request ID、audit、idempotency 與二次確認失敗測試。
- smoke 文件可在非 production 執行，明確記錄 browser、UA、時間、HTTP status、bounded response 與遮罩規則。

## 最小充分驗證

- 受影響 module import／compile、Web Portal tests、shared portal-data contract tests。
- Black／isort 逐檔檢查、`git diff --check`、`git status --short`。
- 不使用 production credentials，不執行 gcloud 或正式資料操作。

## 開始前 checkpoint

Codex 開始實作前回報五行 execution checkpoint；先確認 base/head 與 TASK-090 planning 決策，再建立 task branch commit。
