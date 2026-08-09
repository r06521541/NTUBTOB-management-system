# TASK-092：Phase D qualification and Game operations

task_type: delivery
delivery_group: phase-d-qualification-and-game-operations
requires_independent_pr: true
status: ready_for_codex
owner: work
codex: codex

## 規則來源

產品規則以 `docs/planning/PHASE_D_QUALIFICATION_GAME_DECISIONS.md` 為準；本 TASK 不重新發明 qualification／Game
語意。若可執行程式碼與該文件衝突，先停在 Work review 回報，不自行改變產品規則。

## 目標

完善既有 qualification 與 Game roster／出席／統計操作，讓 team player、guest player、affiliate、staff 的資格
邊界在既有 Game 功能中可被正確管理、顯示、稽核與測試；Event／Activity 延後。

## 範圍

- qualification grant／revoke、有效期間、reason、audit 與 Officer／Admin capability enforcement。
- `team_player`、`guest_player`、`affiliate`、`staff` 的列表、篩選與低敏／管理資料可見性。
- Game invite／roster eligibility、資格來源與已發布 Game 的 roster override／移除歷史。
- team／guest attendance 與 statistics 分流，guest 不污染正式隊員統計。
- 球衣背號規則與目前有效 team_player 的唯一性 contract。
- Game 建立／編輯／取消／改期的既有流程、audit、crawler/manual ownership 與通知 contract；通知只沿用既有受控 caller，
  不在本 TASK 擴大正式發送範圍。
- 將既有 Game／Attendance UI 接上正確 qualification labels 與低敏資料邊界；不做完整視覺重構。

## 非目標

- 不建立 Event／Activity／旅程 schema 或 publish／invitee snapshot。
- 不執行 production deployment、allowlist cutover、正式資料 backfill／mutation、Secret、IAM、Scheduler 或真實通知。
- 不新增欄位或 schema migration，除非 Work 先提出相容 migration／rollback 計畫並取得 Owner 明確批准。
- 不進行整體 Demo 視覺風格改版；Web UI refresh 另立 delivery group。

## 驗收條件

- qualification 狀態與資格期間符合規則文件；授予／撤銷不可繞過 capability、reason、request ID、audit、idempotency。
- inactive／pending／過期 guest 與 affiliate／staff 的 Game eligibility 正確 fail closed。
- 已發布 Game 後資格變更不暗改既有 roster／attendance／statistics；override 與移除保留 audit／歷史。
- team／guest roster、出席與統計清楚分流；正式統計不計入 guest。
- 既有 crawler/manual ownership、改期／取消與通知安全邊界不退化。
- 測試涵蓋成功、拒絕、重試、並發／唯一性、rollback／forward compensation 與資料可見性。

## 最小充分驗證

- 受影響 Web Portal、shared portal-data、attendance／Game callers 的 import／compile 與離線 tests。
- 若涉及 shared library，重建／安裝 shared library 並驗證直接 callers。
- Black／isort 逐檔檢查、`git diff --check`、`git status --short`。

## 開始前 checkpoint

Codex 開始實作前回報五行 execution checkpoint；先逐條對照 `PHASE_D_QUALIFICATION_GAME_DECISIONS.md` 與現行 callers，
遇到規則衝突先停止並回報。
