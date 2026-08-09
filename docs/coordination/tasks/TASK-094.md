# TASK-094：Phase D Real-data Portal UI

task_type: delivery
delivery_group: phase-d-real-data-portal-ui
requires_independent_pr: true
status: ready_for_codex
owner: work
codex: codex

## 目標

將正式資料入口的既有 Game／Attendance 畫面套用已完成的 Demo 視覺語言與資訊架構，並確認頁面實際使用
正式既有 callers／repository data flow；不把 `/demo/*` 的示範資料誤當成正式資料。

## 範圍

- `/future-games` 正式賽程列表與篩選。
- `/game-roster/<game_id>` 正式 roster 顯示。
- `/attendance` 正式出席查詢與回覆流程。
- 套用既有 mobile-first layout、navigation、card、form、status、empty/error state 與中文文案。
- 補 route/template/data-flow contract tests，確認成功、空資料、錯誤、未登入與無權限狀態。
- 確認正式頁面不讀取 `demo_data.py`，並保留 capability、CSRF、session、低敏資料邊界。

## 非目標

- 不修改 qualification／Game domain 規則、schema、migration 或正式資料。
- 不新增 Event／Activity、transport/equipment assignment、通知發送、Flutter、Mobile app 或 OAuth。
- 不部署 production、不操作 Secret、IAM、Scheduler、正式 DB 或真實通知。
- 不以瀏覽器像素檢查取代資料流測試；實際 non-production browser／LINE in-app smoke 另行安排。

## 規則與驗收

- 既有 Game／qualification 規則以 `docs/planning/PHASE_D_QUALIFICATION_GAME_DECISIONS.md` 為準。
- 不改變既有 route、authorization、CSRF、session 或敏感資料可見性。
- 完成受影響 Web Portal unittest、import／compile、逐檔格式檢查與 `git diff --check`。
- report 必須列出正式 route → caller → repository／data source → template 的功能矩陣。

## Execution checkpoint 要求

開始實作前留下五行 checkpoint：目標、核心檔案、關鍵 invariant、最小充分測試、歧義／阻塞。
