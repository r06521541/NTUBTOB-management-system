# TASK-006：建立受控 Production Deployment Runbook

狀態：`completed`
優先級：P1
建立者／執行者：Work（documentation-only）
`base_commit`：`086d663831cf49ddaa5f8413edd8508d1f6bf596`

## 任務目標

依目前 repository 的實際 deployment entry points 建立 `docs/operations/DEPLOYMENT_RUNBOOK.md`，讓未來 production deployment 可以由 Work/Codex準備與執行，但每次仍保留 Owner 的最終批准。

## 範圍

- 盤點 Cloud Run apps、Cloud Functions Gen2、shared library build 與現有測試。
- 定義部署請求摘要、preflight、批准閘門、部署後驗證、停止條件與 rollback。
- 明確區分可安全部署、尚未線上驗證及禁止部署的元件。
- 記錄已確認事實、推論與待確認雲端狀態。
- 結案 TASK-005 merge 狀態並更新協作文件。

## 非目標

- 不執行 gcloud、Cloud Build、Cloud Run/Functions deploy 或流量切換。
- 不查詢、讀取、建立、修改或輪替 Secret。
- 不修改 application code、deployment config、IAM、Scheduler 或 production data。
- 不發送真實 LINE／Discord 訊息。

## 驗收條件

- [x] 涵蓋所有五個部署元件與 shared library。
- [x] 每次 production deploy 都有 Owner 明確批准點。
- [x] 包含 Git、tests、gcloud identity、rollback baseline 與 temporary file 檢查。
- [x] 包含 Cloud Run traffic rollback 與 Functions previous-commit redeploy策略。
- [x] 不把測試成功誤寫為線上整合成功。
- [x] Web Portal Secret/build context blocker 明確標為禁止部署。
- [x] 沒有部署、Secret、通知、資料或雲端 mutation。

## 交付文件

- `docs/operations/DEPLOYMENT_RUNBOOK.md`
- `docs/coordination/tasks/TASK-006.md`
- `docs/coordination/HANDOFF.yaml`
- `docs/coordination/PROJECT_STATE.md`
- `docs/coordination/DECISIONS.md`

## Owner 驗收事項

請 Owner 確認：

1. 是否接受本版 runbook 作為未來 production deployment 的標準流程。
2. 是否同意 Web Portal 在 Secret/build boundary 修正前維持禁止部署。
3. 下一步是否建立 Web Portal deployment blocker 修正，或先做 GCP/Scheduler/IAM 唯讀 inventory。

## Owner 結論

- 2026-08-04：接受本版 runbook 作為未來 production deployment 的標準流程。
- 此接受不包含任何實際部署、gcloud mutation、Secret、IAM、Scheduler、正式通知或 production data 操作授權。
- Web Portal 在 Secret/build boundary 修正前維持禁止部署。
- 下一項任務另行決定。
