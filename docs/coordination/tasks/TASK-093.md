# TASK-093：Phase D Qualification／Game Portal Operations

task_type: delivery
delivery_group: phase-d-qualification-game-portal-operations
requires_independent_pr: true
status: ready_for_codex
owner: work
codex: codex

## 目標

將 qualification 管理介面與既有 Web Portal 的 Game／Attendance 使用流程與資料流做完整，再套用 Demo 的視覺語言，
採 mobile-first 並同步整理資訊架構與導航；不新增 Event／Activity 功能，不改既有產品規則。

## 範圍

- Game／賽程、Attendance、Person 管理、Account 四組頁面。
- Qualification 管理介面：`team_player`、`guest_player`、`affiliate`、`staff` 的摘要、篩選、授予／撤銷、有效期間、
  reason、request ID、audit、history 與 capability enforcement；嚴格遵守既有資格決策文件。
- 盤點並補齊既有 Game 資料流：賽程載入、Game detail、roster、attendance reply／查詢、Game day、
  導航返回、空資料、錯誤與權限拒絕；頁面必須接真實既有 callers／repository contract，不以靜態 fixture 或只換皮
  取代功能。
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
- Qualification 頁面可完成檢視、授予／撤銷與結果 readback；team／guest eligibility 與既有 Game／attendance／statistics
  規則一致，成功、空資料、錯誤、未登入與無權限狀態都有 data-flow contract test。
- 既有 Game 相關流程可從入口一路完成資料讀取／表單提交／結果反映；成功、空資料、錯誤、未登入與無權限狀態都有
  明確 data flow contract test。
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
