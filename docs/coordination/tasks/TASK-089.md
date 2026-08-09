# TASK-089：Phase D identity/admin operations

task_type: delivery
delivery_group: phase-d-identity-admin-operations
requires_independent_pr: true
status: ready_for_codex
owner: work
codex: codex

## 前置條件

- TASK-088 PR #101 已通過 required CI 並整合至 `main`。
- Work 重新確認 integration 後的 exact base commit，再建立 task branch。
- 本 TASK 不因規劃文件或 TASK-088 的非 production smoke 準備而取得 production 權限。

## 目標

把 Phase C 已存在的 identity lifecycle domain 與 TASK-088 的 route transport hardening，收斂成可供管理者
操作、可稽核、可離線驗收的 identity/admin operations。正式 production allowlist cutover 另案處理。

## 範圍

- pending identity 的 match、ignore、reject／blocked 操作完整流程與明確狀態轉移。
- match existing Person／Member、建立 non-member Person、identity remap／qualification 指派的管理 contract。
- Person access level／status 與 qualification 的管理 UI、route-level capability enforcement 與 server-side request reload。
- active admin、last-admin、self-lockout、blocked recovery 的安全規則與 audit atomicity。
- POST-only、session-bound CSRF、固定值／reason／request ID、idempotent retry 與 bounded error handling。
- 管理列表、確認頁、結果頁的最小 UX 與安全資料可見性；不得以 UI 隱藏代替 authorization。
- Person 管理預設先進入可搜尋／分頁列表，再進入個人詳情與編輯頁；pending identity 不混入一般 Person 列表，
  另設待配對／待核可頁面。
- 管理者可從實體校友名冊新增正式 Member／畢業生，並明確建立對應 Person 與初始狀態／資格，不得以登入暱稱推測。
- 中文顯示文字集中管理，至少將 `portal` 顯示為「平台」、`display_name` 顯示為「暱稱」，並同步 account／attendance
  與跨頁面使用點；文案應可集中調整而不散落硬編碼。
- 非 production 測試 fixture／contract tests 與一般瀏覽器、LINE in-app browser smoke 的可執行驗收步驟。

## 非目標

- 不執行 production deployment、production DB DDL/DML、allowlist cutover、正式資料 backfill 或 mutation。
- 不操作 Secret、IAM、Scheduler、Cloud resource，不發送真實 LINE／Discord 通知。
- 不建立 Event／Activity、publish／invitee snapshot、attendance compatibility 或 Google／Apple OAuth。
- 不移除 legacy paths，不將 `Member` 名冊身分與 Person access／qualification 混為一談。

## 驗收條件

- 未配對、未知、disabled／inactive／blocked 與不具 capability 的請求均 fail closed，且副作用前拒絕。
- 每一項 mutation 均具 CSRF、reason、request ID、request-time actor/target reload、audit 同 transaction。
- 不可移除最後一位 active admin；self-lockout 與 blocked recovery 遵守明確核准層級。
- retry 不產生重複或部分 audit；錯誤狀態可安全呈現且不洩漏 token、Secret、完整 provider subject 或資料列。
- 既有 allowlist production behavior 維持不變；route／domain tests 涵蓋成功、拒絕、重試、併發與 atomicity。
- 完成人工 smoke 前置與證據格式；未經 Owner 個別批准不連 production。
- Person 管理 UI 以列表為入口，詳情／編輯為第二層；pending identity 為獨立頁面，且兩者 route authorization 分離。
- 新增 Member 流程具明確欄位、重複／衝突拒絕、audit 與 transaction 邊界。
- 中文措辭在跨頁面 snapshot／contract tests 中一致，且集中文案修改不需逐頁猜測替換。

## 最小充分驗證

- 受影響 Web Portal/shared module import／compile。
- 受影響離線 unit／repository contract／route authorization tests。
- 若涉及 schema 或 migration，另行提出 migration、rollback 與 PostgreSQL matrix 計畫後才擴大範圍。
- `git diff --check`、`git status --short`，並確認未納入 Work-owned 或敏感檔案。

## 外部操作限制

本 TASK 預設只允許本機／CI 離線實作與非 production smoke 準備。任何 production discovery、登入 smoke、DB mutation、
部署、Secret、IAM、Scheduler、Cloud resource 或真實通知，都必須由 Owner 當次明確批准。

## 開始前 checkpoint

Codex 開始實作前必須回報五行 execution checkpoint，並由 Work 確認 TASK-088 已整合後的 exact base/head。
