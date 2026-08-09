# TASK-003：保護 notify-cronjob-service 的 LINE 憑證傳遞

狀態：`completed`
優先級：P1
建立者：Work
`base_commit`：`8d0367ed78579124c37ebda05d655b84207c63ca`
PR 工作包授權：`approved`

## 1. 任務目標

防止 `notify_cronjob_service` 的 LINE 憑證進入 Docker build context 或 container image，改由 Cloud Run runtime Secret Manager binding 提供必要的 `CHANNEL_ACCESS_TOKEN`，並建立可離線及在 Python 3.10 CI 執行的部署契約測試。

## 2. 已確認背景

- Owner 已確認 `notify_cronjob_service` 與 `game_broadcast_service` 使用同一個 LINE 官方帳號發訊息。
- `game_broadcast_service` 已使用 `CHANNEL_ACCESS_TOKEN=CHANNEL_ACCESS_TOKEN:1` 的 Cloud Run Secret Manager binding。
- `notify_cronjob_service` 的部署 target 目前會把完整 `envs/notify_cronjob_service/.env.yaml` 複製到服務目錄。
- 其 Dockerfile 使用 `COPY . .`，且服務目錄目前沒有 `.dockerignore`。
- `notify_cronjob_service/cloudbuild.yaml` 目前只以 Secret Manager 綁定資料庫密碼，未綁定 LINE access token。
- 正式執行路徑會由 shared LINE Messaging client 讀取 `CHANNEL_ACCESS_TOKEN`。
- `CHANNEL_SECRET` 雖出現在 notify cron 的環境設定模組與 example，但目前正式執行路徑沒有使用它。
- 本機 `apps/notify_cronjob_service/.env.yaml` 已被 `.gitignore` 排除、目前未被 Git 追蹤，Git 歷史亦無該檔案。

## 3. 工作範圍

1. 修改 `deploy-notify-cronjob-service` target，在把環境檔複製到 build context 前排除：
   - `CHANNEL_ACCESS_TOKEN`
   - `CHANNEL_SECRET`
2. 修改 `apps/notify_cronjob_service/cloudbuild.yaml`：
   - 保留既有資料庫 Secret binding。
   - 新增 `CHANNEL_ACCESS_TOKEN=CHANNEL_ACCESS_TOKEN:1` runtime Secret binding。
   - 維持 `--no-allow-unauthenticated`。
3. 新增 `apps/notify_cronjob_service/.dockerignore`，至少排除：
   - `.env.yaml`
   - Python cache／bytecode
   - tests 與本機測試檔
   - 不必要的 local artifacts
4. 新增離線部署契約測試，直接查驗 repository 的實際 deployment files。
5. 更新 Python 3.10 GitHub Actions workflow，使既有 game broadcast suite 與新增 notify cron deployment contract suite 都會執行。
6. 建立 Codex report，並依協作流程更新 handoff。

## 4. 明確非目標

- 不部署 Cloud Run、Cloud Build 或任何 GCP 資源。
- 不建立、讀取、顯示、修改、輪替或刪除 Secret Manager value/version。
- 不讀取任何真實 `.env.yaml` 內容；只能使用 `.env_example.yaml` 的 key 名稱。
- 不發送真實 LINE 或 Discord 訊息。
- 不呼叫資料庫、crawler、weather 或其他外部 API。
- 不修改 production IAM、service account、Cloud Scheduler、GitHub repository settings 或 branch protection。
- 不處理 web portal 或 line webhook 的 Secret 傳遞；它們應分成後續任務。
- 不處理 LINE token 輪替；是否輪替由 Owner 另行決定。
- 不重構 notify cron application、shared LINE client 或通知架構。
- 不修正 module import 時計算時間的問題；另立任務處理。

## 5. 驗收條件

- [ ] notify cron deploy target 不會把 `CHANNEL_ACCESS_TOKEN` 或 `CHANNEL_SECRET` 複製進 build context 的 `.env.yaml`。
- [ ] notify cron Cloud Build deploy command 同時保留資料庫密碼 binding，並新增 `CHANNEL_ACCESS_TOKEN=CHANNEL_ACCESS_TOKEN:1`。
- [ ] notify cron Cloud Run 仍維持 private，不得改為 unauthenticated。
- [ ] `.dockerignore` 明確排除 `.env.yaml`。
- [ ] 新增測試會在移除 token binding、移除 credential filter、移除 `.env.yaml` ignore 或改為 public 時失敗。
- [ ] 測試完全離線，且不讀取真實 `.env.yaml`。
- [ ] 既有 game broadcast 17 tests 全部通過。
- [ ] 新增 notify cron deployment contract tests 全部通過。
- [ ] GitHub Actions workflow 會在 Python 3.10 執行兩個 suite，且不增加 secret、write permission、deploy 或外部副作用。
- [ ] `git diff --check` 通過，diff 僅包含任務與協作文件範圍。
- [ ] Codex report 符合 `COLLABORATION.md` 最低要求。

## 6. 必要測試

```text
python -m unittest discover -s apps/game_broadcast_service/tests -v
python -m unittest discover -s apps/notify_cronjob_service/tests -v
git diff --check
git status --short
```

Work 驗收時另需：

- 逐項查驗實際 deployment diff。
- 以 mutation 或等價方式證明新增測試能捕捉四項安全退化。
- 使用 GitHub CLI 查驗 Draft PR checks、Python 版本與兩個 suite 的 job log。

## 7. 安全限制

- `envs/**/.env.yaml` 與服務目錄中的 `.env.yaml` 一律視為真實 Secret，禁止讀取、輸出、複製到報告或加入 Git。
- 測試只能使用 repository deployment text 與明顯假的 fixture 值。
- 不得因測試或 CI 需要而加入 GitHub Secret、GCP credential 或 write permission。
- 不得降低 Cloud Run private 邊界。
- 發現任何已追蹤 Secret、非預期敏感 diff 或需要雲端變更時，立即停止並交回 Owner。

## 8. 預計影響檔案

- `makes/deploy_apps.mk`
- `apps/notify_cronjob_service/cloudbuild.yaml`
- `apps/notify_cronjob_service/.dockerignore`
- `apps/notify_cronjob_service/tests/__init__.py`
- `apps/notify_cronjob_service/tests/test_deployment_contract.py`
- `.github/workflows/python-tests.yml`
- `docs/coordination/reports/TASK-003-CODEX.md`
- `docs/coordination/HANDOFF.yaml`

不應修改 application code、requirements、database model/schema 或其他服務的 deployment config。

## 9. 已知風險與假設

- Owner 已確認兩個服務共用 LINE 官方帳號，因此規格沿用 repository 既有 `CHANNEL_ACCESS_TOKEN` Secret 名稱與 version 1 binding。
- Work 尚未查詢 GCP，無法確認 Secret version 1 是否仍 enabled、內容是否正確或 runtime service account 是否有 accessor IAM。
- 靜態測試與 CI 不能證明 Cloud Build、container layer 或 Cloud Run runtime 的線上整合正確。
- `.dockerignore` 與文字式 deployment tests 可能對格式調整敏感；測試應檢查安全語意，不應綁死無關空白。
- 本機憑證曾在 2026-08-04 的工具輸出中短暫出現；是否輪替仍由 Owner 決定，不能在本任務自行操作。

## 10. Owner 決策事項

Owner 需決定：

- 是否批准 TASK-003 的範圍與驗收條件。
- 是否同時批准 DEC-004 定義的 PR 工作包：branch、commit、push、Draft PR、CI 查驗及同一 PR 內的驗收文件更新。
- 是否另立憑證輪替任務；這不阻擋 repository-only TASK-003。

即使批准 PR 工作包，仍不包含 merge、部署、Secret 操作、正式通知或不可逆資料操作。

Owner 已於 2026-08-04 批准 TASK-003 與 DEC-004 定義的 PR 工作包。憑證輪替仍為獨立待決事項，不屬於本任務授權。

## 11. Codex 完成要求

Codex 完成後必須：

1. 建立 `docs/coordination/reports/TASK-003-CODEX.md`。
2. 記錄實際修改、完整測試輸出摘要、未執行項目、風險與 Secret／部署影響聲明。
3. 若 PR 工作包已批准，建立任務 branch、commit、push 並建立或更新 Draft PR。
4. 更新 `HANDOFF.yaml` 為：
   - `status: ready_for_review`
   - `next_actor: work`
5. 不得 merge、deploy、操作 Secret 或發送通知。
