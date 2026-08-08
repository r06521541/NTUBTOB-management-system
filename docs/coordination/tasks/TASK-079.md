# TASK-079：固定 LINE 通知服務的新版 Token 部署契約

## 目標

把 `game-broadcast-service` 與 `notify-cronjob-service` 的 Cloud Build 部署設定，從已撤銷的
`CHANNEL_ACCESS_TOKEN:1` 改為目前有效的 `CHANNEL_ACCESS_TOKEN:2`。此任務只修正 repository
中的未來部署契約與離線測試；不部署、不讀取或修改 Secret、也不觸發通知。

## 背景與已確認事實

- Owner 已完成 LINE Messaging channel 的 access token 輪替；目前有效版本為 Secret Manager
  `CHANNEL_ACCESS_TOKEN:2`，version 1 不應再被新的部署使用。
- 2026-08-08 的唯讀盤點與後續最小 runtime 更新已確認兩個現行 Cloud Run revision 都綁定 version 2。
- 但 repository 的兩份 Cloud Build 設定仍釘住 version 1。若未來依原設定重新部署，會把服務重新綁回已撤銷的
  credential，造成 LINE 通知失敗。
- `CHANNEL_SECRET` 僅為 LINE webhook 的 signature 驗證需求；本任務不調整該 service 或 Web Portal 的
  LINE Login secret。

## 範圍

1. 修改下列兩份 active Cloud Build deployment contract：
   - `apps/game_broadcast_service/cloudbuild.yaml`
   - `apps/notify_cronjob_service/cloudbuild.yaml`
2. 將相鄰 deployment-contract tests 的預期值更新為 version 2，並搜尋 active deployment 設定，確保沒有其他
   `CHANNEL_ACCESS_TOKEN:1` 會在未來部署時生效。
3. 執行兩個服務的受影響離線測試、deployment tooling tests、靜態／格式檢查與 `git diff --check`。
4. 撰寫 Codex report，更新 handoff 為 `ready_for_review / work`，並透過跨 session 通知 Work。

## 非目標與禁止事項

- 不讀取真實 `.env.yaml`、Secret payload 或 Secret metadata；不得建立、啟用、停用、輪替或刪除 Secret versions。
- 不執行 Cloud Build、Cloud Run deploy、revision／traffic／Scheduler／IAM 變更、production invoke 或任何通知。
- 不變更 LINE webhook、Web Portal、資料庫、schema、runtime flags 或 shared library。
- 不修改歷史 deployment record；僅修 active deployment config 與直接保護它的測試。

## 驗收條件

- 兩份 active Cloud Build 設定都只以 `CHANNEL_ACCESS_TOKEN=CHANNEL_ACCESS_TOKEN:2` 綁定 LINE token。
- 對 active deployment config 的搜尋不再找到 `CHANNEL_ACCESS_TOKEN:1`。
- 兩個服務的 deployment contract tests，以及受影響 deployment tooling tests 通過。
- 本機不使用 bundled Windows Python 的 Black CLI；若本輪變更 Python，依 `AGENTS.md` 用專案指定 Black formatter API
  做本次變更檔案的內容比對；本任務預期只變 YAML／測試文字。
- `git diff --check` 通過，沒有未說明的檔案變更或外部副作用。

## 後續部署邊界（不屬於本任務）

合併後，notify 的程式 source 仍可能落後於 TASK-077 的 Phase C feature-off artifact。若要讓 notify 取得該
新版 source，必須另建 deployment task，重新盤點 exact source commit、build artifact、current/rollback revision、
runtime flags 與 Scheduler boundary，並取得 Owner 對 production build/deploy/traffic 的明確批准。不得因本任務
完成而自動部署。

## 協作

- Base commit：`1838ec6fc77a74e23700f9cd29b8ea910c0a29fb`
- Codex 實作、測試、commit、push、report 與交回 Work；不得自行部署或建立 PR。
- Work 查驗實際 diff 與測試後，依 standing Git authorization 建立唯一 ready PR、查驗 hosted CI 並 merge。
- 這是兩個 Cloud Build config 與其 contract test 的變更；最小充分 hosted CI 應覆蓋受影響服務與 deployment tooling，
  不應因無 schema／migration／model／SQL 變更而要求 PostgreSQL matrix。
