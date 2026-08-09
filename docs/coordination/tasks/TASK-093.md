# TASK-093：Phase D Web Portal UI refresh

task_type: delivery
delivery_group: phase-d-web-ui-refresh
requires_independent_pr: true
status: ready_for_codex
owner: work
codex: codex

## 目標

將既有 Web Portal 的主要使用流程套用 Demo 的視覺語言，採 mobile-first，並同步整理資訊架構與導航；不新增
Event／Activity 功能，不改既有產品規則。

## 範圍

- Game／賽程、Attendance、Person 管理、Account 四組頁面。
- 統一 Demo 風格的 layout、navigation、card、form、status badge、empty/loading/error state 與 responsive behavior。
- 重新整理跨頁導航與頁面階層，保留既有 route／capability／CSRF／session 行為。
- 延續集中式中文文案：平台、暱稱與後續可調整 labels。
- 低敏資料邊界維持不變；不因視覺重構顯示電話、醫療、私人備註、provider subject 或 Secret。
- 建立 mobile viewport／route contract／accessibility-oriented tests，並保留 desktop fallback。

## 非目標

- 不建立 Event／Activity、通知發送、Flutter、Mobile app、Google／Apple OAuth 或新的登入 provider。
- 不修改 qualification／Game domain 規則、schema、migration、production data、allowlist、Secret、IAM、Scheduler。
- 不執行 production deployment 或人工 production smoke。

## 驗收條件

- 主要頁面在 mobile-first viewport 具一致導航、可操作表單、清楚狀態與錯誤回饋。
- Basic／Officer／Admin 的 route capability 與資料可見性不退化；UI 隱藏不是 authorization boundary。
- Game／Attendance／Person／Account 的中文措辭、按鈕、空狀態與返回導覽跨頁一致。
- 不引入外部 CDN、敏感資料或新的 production runtime dependency。
- 測試涵蓋主要 route render、登入／拒絕、表單 CSRF、mobile navigation 與既有 callers。

## 最小充分驗證

- Web Portal 完整 unittest、受影響 template／route contract tests。
- HTML／CSS 靜態檢查、py_compile、Black／isort 逐檔檢查、`git diff --check`。
- 不執行 production、gcloud、Secret、正式資料或真實通知。

## 開始前 checkpoint

Codex 開始實作前回報五行 execution checkpoint，先盤點現有 Demo tokens／CSS／templates 與四組頁面 callers，避免無關重構。
