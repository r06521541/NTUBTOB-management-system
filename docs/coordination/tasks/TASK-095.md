# TASK-095：Phase D Game Dashboard Rebuild

task_type: delivery
delivery_group: phase-d-game-dashboard-rebuild
requires_independent_pr: true
status: ready_for_codex
owner: work
codex: codex

## 目標

重新設計正式比賽資訊體驗：盤點並取代既有 `/future-games`、`/game-roster/<game_id>`、`/attendance` 三個分散頁面，
以單一正式比賽 dashboard 集中呈現該場比賽的完整資訊與互動流程。頁面可大幅參考 Demo layout，但資料必須來自正式
Game／Member／Attendance callers，不得使用 demo fixture。

## 正式資訊架構

- 比賽列表：保留賽程入口，點選一場比賽後進入正式 dashboard。
- 比賽 dashboard：暫定 route `/games/<game_id>`；呈現比賽摘要、日期／場地／對手、目前出席統計、已回覆名單、未回覆狀態、
  roster 概覽、個人出席回覆入口與返回賽程導航。
- 舊 `/game-roster/<game_id>` 與 `/attendance` 若保留，必須導向或以相容方式進入 dashboard，不得維持三套分散 UI。
- `/future-games` 改為正式比賽列表入口，使用新版 dashboard 導航；不讀取 `/demo/*` 資料。

## 介面要求

- mobile-first、Demo 風格但可自行創造更豐富的 dashboard layout。
- 使用清楚的資訊階層、card／status、空資料、錯誤、未登入、無權限狀態與可操作的 touch controls。
- 集中中文文案，使用「平台」與「暱稱」等既有一致措辭。
- 不引入 CDN 或新的 runtime dependency；保留 accessibility/focus-visible 基線。

## 資料流與安全 invariant

- 以 `docs/planning/PHASE_D_QUALIFICATION_GAME_DECISIONS.md` 為比賽／資格規則來源。
- 正式資料只經既有 Game、Member、Attendance callers／repository；不得以靜態 fixture 或 Demo data 取代。
- 保留 authentication、capability、CSRF、session、request-time reload 與低敏資料邊界。
- attendance reply 必須維持既有 POST／PRG／CSRF 行為；roster 顯示不可擴大敏感資料暴露。
- 不在本 task 修改 qualification domain rules、schema、migration 或正式資料。

## 非目標

- 不新增 Event／Activity、transport/equipment assignment、通知發送、Flutter、Mobile app、OAuth 或多重登入途徑。
- 不部署 production、不操作 Secret、IAM、Scheduler、正式 DB 或真實通知。
- 不做 browser／LINE in-app smoke；另行建立驗收 task。

## 驗收條件

- 完整驗證列表→dashboard→attendance reply→PRG/readback 的正式 data flow。
- Dashboard 成功、無賽事／無回覆、game not found、未登入、無權限與 malformed input 均有 contract tests。
- 受影響 Web Portal unittest、import／py_compile、逐檔 Black/isort、`git diff --check` 通過。
- report 列出 route → caller → repository/data source → template 的功能矩陣，以及明確未驗證項目。

## Execution checkpoint 要求

開始實作前留下五行 checkpoint：目標、核心檔案、關鍵 invariant、最小充分測試、歧義／阻塞。
