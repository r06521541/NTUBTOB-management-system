# TASK-001：建立 game-broadcast-service P0 部署契約回歸測試

狀態：`completed`
優先級：P1
建立者：Work
`base_commit`：`f1884bfbe903e4b24fa82ae6cf19c86167d06ee2`

## 1. 任務目標

新增完全離線、可重複執行的測試，鎖定 `game-broadcast-service` P0 已建立的部署安全契約，避免後續修改再次造成必要 Secret 漏綁、敏感環境欄位進入一般部署檔或 Docker image、或 Cloud Run private 邊界退化。

## 2. 背景與現況

P0 目前包含三個連續修正：

- `0521a02`：氣象 API key 改由 runtime environment/Secret Manager 取得，並補上氣象錯誤處理與降級測試。
- `9d99cfb`：加入 `apps/game_broadcast_service/.dockerignore`。
- `f1884bf`：Cloud Run 綁定 LINE access token，部署前排除 LINE token/secret。

現有 13 個 unittest 涵蓋氣象設定、HTTP 錯誤、回應驗證與提醒降級，但沒有測試 `f1884bf` 的部署設定。這代表部署設定可能在未被測試察覺的情況下回歸。

Repository 起始狀態包含 Owner/Work 建立但尚未追蹤的 `AGENTS.md` 與 `docs/`。Codex 必須保留它們，不得刪除、覆寫或把無關內容納入程式修改。

## 3. 工作範圍

- 在 `apps/game_broadcast_service/tests/` 新增部署契約測試，例如 `test_deployment_contract.py`。
- 測試必須直接讀取 repository 中的實際檔案：
  - `apps/game_broadcast_service/cloudbuild.yaml`
  - `apps/game_broadcast_service/.dockerignore`
  - `makes/deploy_apps.mk`
- 測試至少驗證：
  1. Cloud Run deploy command 綁定 `DSN_PASSWORD`、`WEATHER_API_KEY`、`CHANNEL_ACCESS_TOKEN`。
  2. game broadcast deploy target 產生一般環境檔時，會排除 `CHANNEL_ACCESS_TOKEN` 與 `CHANNEL_SECRET`。
  3. `.dockerignore` 排除 `.env.yaml`。
  4. `game-broadcast-service` 維持 `--no-allow-unauthenticated`。
- 優先使用 Python 3.10 standard library；不得只為解析這些小型設定檔新增 production dependency。
- 若現有 unittest discovery 可自動找到新測試，不修改 Makefile；只有確實無法 discover 時才允許最小調整測試入口。
- 必要時更新與此測試直接相關的測試說明，但不得擴張成整體 README 重寫。
- 完成實作後建立 `docs/coordination/reports/TASK-001-CODEX.md`，並依協作流程更新 `HANDOFF.yaml`。

## 4. 明確非目標

- 不修正或重構 P0 部署流程本身；若測試發現缺陷，先在 Codex report 回報並將任務標記為 blocked/需 Work 判斷。
- 不處理其他 apps/functions 的 Secret 傳遞。
- 不修改 LINE 訊息、收件範圍、排程、資料庫或 application business logic。
- 不引入 CI 平台、migration framework、部署框架或大型重構。
- 不處理 Git 歷史中的舊 credential。

## 5. 驗收條件

- [ ] 新增測試直接檢查實際 Cloud Build、Docker ignore 與 deployment Makefile，不只測試複製出的 fixture。
- [ ] 移除任一必要 Secret 綁定時，對應測試會失敗。
- [ ] 移除 `CHANNEL_ACCESS_TOKEN` 或 `CHANNEL_SECRET` 的排除條件時，對應測試會失敗。
- [ ] `.dockerignore` 不再排除 `.env.yaml` 時，對應測試會失敗。
- [ ] Cloud Run 改為 unauthenticated 時，對應測試會失敗。
- [ ] 現有 13 個 game reminder 測試仍通過。
- [ ] 全部測試使用 synthetic/fake 資料，沒有網路、DB、GCP、LINE、Discord 或 weather 呼叫。
- [ ] 保持 Python 3.10 相容；若執行環境沒有 Python 3.10，Codex 必須回報實際版本與未驗證風險，不得宣稱已驗證 3.10。
- [ ] `git diff --check` 通過。
- [ ] 實際 diff 只包含任務範圍內的測試、必要的最小測試說明、Codex report 與 handoff 更新。
- [ ] Codex report 符合 `COLLABORATION.md` 第八節最低要求。

## 6. 必要測試

至少執行：

```sh
python -m unittest discover -s apps/game_broadcast_service/tests -v
git diff --check
git status --short
```

若 Windows 沒有 `python`，可使用工作區提供的 Python executable，但必須在 report 記錄完整命令與版本。不要為了執行測試修改 Makefile。

## 7. 安全限制

- 不讀取任何真實 `.env.yaml`；只可讀 `.env_example.yaml` 的 key 名稱，但本任務預期不需要。
- 不讀取、列出或修改 Secret Manager、IAM、Cloud Run、Cloud Functions、Cloud Scheduler 或 Cloud Build 資源。
- 不執行 `make deploy-*`、`gcloud builds submit`、`gcloud functions deploy` 或其他部署命令。
- 不連線 production/staging DB 或任何外部 API。
- 不發送真實 LINE/Discord 訊息。
- 測試與 report 不得包含真實 token、secret、password、完整 webhook URL 或外部 response body。
- 不 commit、push、建立 PR 或 merge，除非 Owner 另行明確要求。

## 8. 相關檔案與模組

- `AGENTS.md`
- `docs/coordination/COLLABORATION.md`
- `docs/coordination/HANDOFF.yaml`
- `docs/coordination/PROJECT_STATE.md`
- `apps/game_broadcast_service/cloudbuild.yaml`
- `apps/game_broadcast_service/.dockerignore`
- `makes/deploy_apps.mk`
- `apps/game_broadcast_service/tests/test_game_reminder.py`
- `Makefile`

## 9. 已知風險

- 使用純文字檢查 deployment command 容易與排版耦合；測試應鎖定語意所需的最小片段，避免要求不重要的空白或換行格式。
- YAML parser 不是現有 production dependency；為此新增 dependency 的成本高於任務價值。
- 靜態測試只能證明 repository 契約，不能證明 Secret version、IAM、Cloud Build 或 Cloud Run 線上行為正確。
- `base_commit` 與程式碼 HEAD 相同，但 working tree 有未追蹤的 Owner/Work 文件；Codex 必須保留並清楚區分既存變更與本次變更。

## 10. 需要 Owner 決策的事項

- 本任務開始前沒有產品或雲端決策依賴，可直接由 Codex 執行。
- P0 是否部署、是否查詢/輪替 Secret、是否做真實 LINE smoke test均不在本任務內，之後仍需 Owner 明確批准。

## 11. Codex 交付與交棒

Codex 完成後必須：

1. 建立 `docs/coordination/reports/TASK-001-CODEX.md`。
2. 記錄實際修改、命令、測試結果、Python 版本、未驗證事項、working tree 與 deployment/Secret 影響。
3. 更新 `docs/coordination/HANDOFF.yaml`：
   - `status: ready_for_review`
   - `next_actor: work`
   - `head_commit` 填實際 HEAD；若沒有新 commit，仍填目前 HEAD，並在 note 說明成果為未提交 diff。
4. 不自行接受任務或把狀態設為 completed。
