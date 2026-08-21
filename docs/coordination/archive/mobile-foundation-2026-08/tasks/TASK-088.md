# TASK-088：Phase D identity/admin transition 與人工登入 smoke

task_type: delivery
delivery_group: phase-d-identity-admin-transition
requires_independent_pr: true
status: ready_for_codex
owner: work
codex: codex

## 目標

在 Phase C 已完成的 Person／identity／qualification 基礎上，交付可離線驗收的 Phase D
identity/admin transition foundation，並納入一般瀏覽器與 LINE in-app browser 的人工登入 smoke
驗收準備。保留既有 production allowlist 作為目前正式管理權限來源；本 TASK 不執行 production cutover。

## 範圍

- pending identity 的 match／ignore／reject domain flow、權限檢查與 append-only audit contract。
- Person access/status、identity 與 qualification 管理所需的安全 domain／repository／route contract，
  視現有程式邊界以最小可驗收切片實作。
- `basic`／`officer`／`admin` capability policy 與既有 `member` 相容 adapter 的明確行為。
- last-admin、self-lockout、request-time reload、CSRF、reason、idempotency 與 transaction atomicity。
- 管理入口 UI／route-level enforcement；UI 隱藏不得作為 authorization boundary。
- 人工登入 smoke 的執行前置、驗收腳本或測試證據格式，涵蓋一般瀏覽器與 LINE in-app browser；不在本機或 CI
  連接 production、發送真實通知或執行正式 mutation。
- 同步 coordination 文件的 repository base/head：base 為
  `d2888c440563b2d3beff95b0072f1a864e841889`，head 以交棒時實際 commit 為準。

## 非目標

- 不執行 production deployment、production DB DDL/DML、Secret／IAM／Scheduler／Cloud resource 操作。
- 不進行 allowlist 的 production cutover、角色正式回填或任何正式資料 mutation。
- 不發送真實 LINE／Discord 通知。
- 不建立 Event／Activity schema、publish、invitee snapshot 或 attendance compatibility contract。
- 不移除 legacy paths；不處理 Google／Apple OAuth 實作。

## 驗收條件

- 未配對、未知狀態／access／qualification、disabled／inactive／blocked 均 fail closed。
- 所有管理 mutation 在 domain 與 route 層皆驗證 active admin／capability、CSRF、reason、request ID，並與 audit
  同 transaction；不可移除最後一位 active admin。
- pending identity 只能 match 既有 Person／Member、建立 non-member Person 或 reject／blocked，不能依 display name
  自動推測身分、資格或 access。
- 既有 allowlist-based production behavior 維持相容；未獲批准不得改變正式權限來源。
- 瀏覽器 smoke 的 manual-only boundary、前置條件、成功／失敗證據與未驗證風險清楚記錄，不宣稱已完成 production
  smoke，除非 Owner 另行批准並實際執行。
- Codex 完成 report、測試、`git diff --check`、`git status --short`，並提交描述性 commit 到 task branch。

## 最小充分驗證

- 受影響 Python module import／compile 檢查。
- 受影響離線 unit／contract tests，涵蓋成功、拒絕、重試、併發／last-admin 與 audit atomicity。
- 若修改 Web Portal，執行其可離線測試與 route-level authorization checks。
- `git diff --check` 與 `git status --short`。

## 外部操作限制

本 TASK 不授權部署、production discovery、production DB mutation、Secret、IAM、Scheduler、Cloud resource 或真實
通知。若需要人工 production smoke，Codex 必須先交回準備好的步驟與 blocker，由 Owner 當次明確批准後另行執行。

## Execution checkpoint（Codex 開始實作前回報）

Codex 必須先回報五行 checkpoint：目標、核心檔案、關鍵 invariant、最小充分測試、歧義／阻塞。
