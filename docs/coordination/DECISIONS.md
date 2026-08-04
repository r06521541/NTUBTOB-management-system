# 專案決策紀錄

## DEC-001：接受 TASK-001 結案

- 日期：2026-08-04
- 決策者：Owner
- 狀態：accepted
- 決策：Owner 接受 TASK-001 的 Work 驗收結論，任務正式結案。
- 驗收證據：完整 unittest 17/17 通過，四項部署契約 mutation checks 均能捕捉回歸。
- 已知限制：尚未以可用的 Python 3.10 runtime 實跑，也未執行 Black、Docker build、Cloud Build 或線上整合驗證。
- 不包含的授權：此決策不批准 stage、commit、push、PR、部署、Secret 操作或真實 LINE/Discord 通知。
- 後續事項：是否建立 Python 3.10 CI 尚未決定；若要執行，應另立任務並定義 CI 平台與觸發條件。

## DEC-002：建立最小 Python 3.10 CI

- 日期：2026-08-04
- 決策者：Owner
- 狀態：approved
- 決策：建立 GitHub Actions workflow，以 Python 3.10 自動執行目前的 `game_broadcast_service` 完整 unittest suite。
- 範圍：只建立測試 CI；使用 repository read-only 權限，不使用 Secrets，不包含部署、發布、GCP 或真實外部服務。
- 觸發：pull request、push 到 main，以及手動 `workflow_dispatch`。
- 安全要求：官方 actions pin 到完整 commit SHA，不使用 `pull_request_target` 或 write permissions。
- 不包含的授權：不批准 commit、push、啟用/修改 repository Actions settings、branch protection、部署或 Secret 操作。
- 實作任務：`TASK-002`。

## DEC-003：接受 TASK-002 結案並建立 commit

- 日期：2026-08-04
- 決策者：Owner
- 狀態：accepted
- 決策：Owner 接受 TASK-002 的 Work 驗收結論，任務正式結案，並授權將 TASK-002 workflow 與協作文件建立為 commit。
- 驗收證據：本機 unittest 17/17 通過；workflow 安全與規格靜態檢查通過；官方 action release commit SHA 已查證。
- 已知限制：尚無 GitHub workflow parser 與 Python 3.10 hosted runner 的實跑證據；第一次 push 並建立 PR 後仍需確認線上 CI。
- 不包含的授權：不批准 push、PR、merge、部署、Secret 操作、正式 LINE/Discord 通知或其他雲端資源變更。
