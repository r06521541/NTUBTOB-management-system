# TASK-003 Codex 實作報告

## 任務狀態

- 狀態：`blocked`
- base commit：`8d0367ed78579124c37ebda05d655b84207c63ca`
- 實作 commit：`4efe1c57d64ac6e22cf0ed1d9608f9384ca5e2cd`
- branch：`codex/task-003-notify-secret-boundary`
- branch push：已成功 push 至 `origin/codex/task-003-notify-secret-boundary`
- Draft PR：尚未建立；本機沒有 GitHub CLI，內建瀏覽器因 sandbox 權限無法啟動。

## 實際修改內容

- `deploy-notify-cronjob-service` 改為產生非敏感環境檔，排除 `CHANNEL_ACCESS_TOKEN` 與 `CHANNEL_SECRET`。
- notify cron Cloud Run deploy command 保留既有資料庫密碼 binding，並新增既定的 `CHANNEL_ACCESS_TOKEN=CHANNEL_ACCESS_TOKEN:1` runtime binding。
- Cloud Run 保持 `--no-allow-unauthenticated`。
- 新增 notify cron `.dockerignore`，排除 `.env.yaml`、Python cache/bytecode、tests 與本機測試 artifacts；保留 Dockerfile 所需的 shared library `dist` artifact。
- 新增 4 個完全離線的 deployment contract tests，直接查驗 repository 實際 deployment files。
- Python 3.10 GitHub Actions workflow 增加 notify cron deployment contract suite，保留既有 read-only 權限及無 Secret、無部署邊界。

## 修改檔案

實作 commit：

- `.github/workflows/python-tests.yml`
- `apps/notify_cronjob_service/.dockerignore`
- `apps/notify_cronjob_service/cloudbuild.yaml`
- `apps/notify_cronjob_service/tests/__init__.py`
- `apps/notify_cronjob_service/tests/test_deployment_contract.py`
- `makes/deploy_apps.mk`

協作文件：

- `docs/coordination/COLLABORATION.md`（Work 既存變更）
- `docs/coordination/DECISIONS.md`（Work 既存變更）
- `docs/coordination/PROJECT_STATE.md`（Work 既存變更）
- `docs/coordination/reviews/TASK-002-WORK.md`（Work 既存變更）
- `docs/coordination/tasks/TASK-003.md`（Work 既存任務規格）
- `docs/coordination/reports/TASK-003-CODEX.md`（本報告）
- `docs/coordination/HANDOFF.yaml`（本次 blocker 交接）

## 執行過的命令與結果

1. Branch 與基準：

   ```text
   git switch -c codex/task-003-notify-secret-boundary 8d0367ed78579124c37ebda05d655b84207c63ca
   ```

   結果：成功，且保留 Work 未提交協作文件。

2. Game broadcast tests：

   ```text
   python -m unittest discover -s apps/game_broadcast_service/tests -v
   ```

   結果：Python 3.12.13，17/17 通過。

3. Notify cron deployment contract tests：

   ```text
   python -m unittest discover -s apps/notify_cronjob_service/tests -v
   ```

   結果：4/4 通過。

4. Mutation checks：

   - 移除 access token runtime binding：被測試捕捉。
   - 移除 credential filter：被測試捕捉。
   - 移除 `.env.yaml` Docker ignore：被測試捕捉。
   - 把 Cloud Run private flag 改為 public：被測試捕捉。

5. 相容性與 workflow 靜態檢查：

   - 新測試 Python 3.10 grammar check：通過。
   - Workflow 同時包含兩個指定 suites：通過。
   - Workflow 未增加 Secrets、write permission、GCP、deploy 或 publish：通過。

6. Git：

   ```text
   git diff --check
   git diff --cached --check
   git push -u origin codex/task-003-notify-secret-boundary
   ```

   結果：diff checks 通過；實作 commit 已成功 push。

## 未執行或無法執行的測試

- 未執行 Docker build、Cloud Build、Cloud Run deploy、image layer scan 或任何 GCP 線上檢查。
- 未讀取或驗證 Secret version 1 的 enabled 狀態、內容或 service account IAM。
- 尚未有 TASK-003 GitHub Actions run，因 Draft PR 尚未建立。
- 本機 runtime 是 Python 3.12.13；Python 3.10 將由 Draft PR CI 驗證。
- 未執行 Black；可用 Python runtime 沒有安裝 Black，本任務亦未修改 application formatting。

## 安全與影響聲明

- 沒有讀取任何 `.env.yaml` 或 Secret value。
- 沒有連線 DB、LINE、Discord、crawler、weather 或其他外部 API。
- 沒有部署、修改 GCP/GitHub settings、輪替憑證、發送通知、執行 migration 或 merge。
- 本任務修改 repository deployment config，但沒有修改任何正式 runtime 或雲端資源。
- 不涉及 database model、schema 或 migration。

## 假設、風險與阻礙

- 依 Owner 決策，notify cron 與 game broadcast 共用同一 LINE 官方帳號，因此沿用既有 Secret 名稱與 version 1 binding。
- 靜態測試不能證明正式 Secret、IAM、Cloud Build、image 或 Cloud Run runtime 正確。
- `.dockerignore` 沒有排除 `dist/`，因 Dockerfile 必須從該目錄安裝 shared library artifact。
- Blocking issue：本機沒有 `gh` CLI；內建瀏覽器因 Windows sandbox 對使用者資料路徑的存取限制無法啟動。branch 已 push，但需要 Owner 手動建立 Draft PR，或提供可用的 GitHub CLI/browser 後再交回 Codex。

## 下一步

Owner 可由下列頁面建立 Draft PR，base 選擇 `main`：

`https://github.com/r06521541/NTUBTOB-management-system/pull/new/codex/task-003-notify-secret-boundary`

Draft PR 建立後，將 `HANDOFF.yaml` 交回 `codex`，Codex 再確認 PR/CI 並交給 Work review；不得 merge 或部署。
