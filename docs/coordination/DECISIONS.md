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

## DEC-004：採用 Draft PR 一次授權流程

- 日期：2026-08-04
- 決策者：Owner
- 狀態：accepted
- 問題：原流程需要 Owner 分別處理或批准 commit、push、建立 PR、CI 查驗及合併後證據更新，造成多次人工交接，也容易在 merge 後才補驗收文件。
- 決策：一般任務可在 Owner 批准任務時，同時批准該任務的「PR 工作包」，讓 Codex 與 Work 依序完成 branch、commit、push、Draft PR、CI 查驗及同一 PR 內的驗收文件更新。
- 必要紀錄：每個任務是否取得 PR 工作包授權，必須明確寫入任務文件或本決策紀錄；未記錄即視為未授權。
- 最終控制：Work 驗收及最終 CI 成功後，仍須交回 Owner 決定是否 merge。
- 永久排除：PR 工作包不包含 merge、直接寫入 default branch、部署、release、Secret、GitHub repository/organization 設定、正式通知、不可逆資料操作或重大架構變更。
- 流程文件：`docs/coordination/COLLABORATION.md` 版本 1.1，第十四節。

## DEC-005：notify cron 與 game broadcast 共用 LINE 官方帳號

- 日期：2026-08-04
- 決策者：Owner
- 狀態：confirmed
- 決策：`notify_cronjob_service` 與 `game_broadcast_service` 使用同一個 LINE 官方帳號發送訊息。
- TASK-003 影響：notify cron 的 repository deployment config 可沿用既有 `CHANNEL_ACCESS_TOKEN` Secret Manager 名稱與 version 1 binding，不建立新的 Secret。
- 限制：此決策不證明 GCP Secret version、內容或 IAM 正確，也不授權讀取、修改或輪替 Secret。

## DEC-006：批准 TASK-003 與 PR 工作包

- 日期：2026-08-04
- 決策者：Owner
- 狀態：approved
- 決策：批准 `TASK-003` 的範圍、驗收條件與 DEC-004 定義的 PR 工作包。
- 已授權：任務 branch、任務範圍內 commit、push、建立或更新 Draft PR、唯讀 CI 查驗，以及在同一 PR 更新驗收文件。
- 未授權：merge、直接寫入 default branch、部署、Secret 讀取或修改、憑證輪替、正式通知、不可逆資料操作或重大架構變更。
- 憑證輪替：仍為獨立待決事項，不阻擋 repository-only TASK-003。

## DEC-007：接受並合併 TASK-003

- 日期：2026-08-04
- 決策者：Owner
- 狀態：accepted
- 決策：Owner 接受 TASK-003 的 Work 驗收結論，授權將 PR #26 標記 ready 並 merge。
- 結果：PR #26 已以 merge commit `9b812f5c476d804b434e484ea7f4e8bfd299bfa4` 合併。
- Merge 標題：`security(notify-cron): keep LINE credentials out of images`。
- 驗收證據：最終 Actions run `30917468698` 成功；Python 3.10.20 下 game broadcast 17/17、notify cron 4/4 通過。
- 不包含的授權：未批准部署、Secret 操作、憑證輪替、正式通知或不可逆資料操作。

## DEC-008：採用描述性 commit 與 PR 標題

- 日期：2026-08-04
- 決策者：Owner
- 狀態：accepted
- 問題：以 `TASK-xxx`、handoff 或 update files 為標題，離開協作文件後無法理解 commit 的實際目的。
- 決策：commit、PR 與 merge commit 標題必須描述受影響元件及主要行為／結果；優先採用 `<type>(<scope>): <outcome>`。
- TASK 編號：只放在 commit body/footer 或 PR 說明中作為追溯資訊，不得取代描述性標題。
- 執行規則：Codex 建立 commit 前自行檢查，Work 驗收 commit/PR 時再次檢查；不合規時應在 merge 前改寫或補正。
- 流程文件：`AGENTS.md` 與 `docs/coordination/COLLABORATION.md` 版本 1.2，第十五節。

## DEC-009：批准賽程隊伍篩選修正與 PR 工作包

- 日期：2026-08-04
- 決策者：Owner
- 狀態：approved
- 決策：批准 TASK-004，修正 `update_game_schedule` 在日期篩選時丟失隊伍條件的錯誤，並新增純函式測試與 Python 3.10 CI coverage。
- 行為邊界：維持隊名完全相等、起訖時間皆包含、保留輸入順序；不新增隊名 alias 或正規化。
- PR 工作包：批准 branch、描述性 commits、push、Draft PR、CI 查驗及同一 PR 驗收文件更新。
- 未授權：merge、部署、Secret、正式通知、production data、不可逆操作或重大架構變更。
- 任務文件：`docs/coordination/tasks/TASK-004.md`。
