# TASK-003 Work 驗收報告

驗收時間：2026-08-04T22:07:23+08:00
驗收者：Work
驗收結論：`accepted`
下一位角色：`owner`

## 1. 驗收基準

- branch：`codex/task-003-notify-secret-boundary`
- task base commit：`8d0367ed78579124c37ebda05d655b84207c63ca`
- 實作 commit：`4efe1c57d64ac6e22cf0ed1d9608f9384ca5e2cd`
- Codex handoff commit：`2c6ceee77034a41ffe7d72b877f7c63a3dc4c724`
- Draft PR：[#26](https://github.com/r06521541/NTUBTOB-management-system/pull/26)
- Work 開始驗收時 repository 乾淨，branch 與 remote head 一致。
- Work 已直接查驗實際 diff、commits、PR、CI job log、deployment files 與 tests，沒有只依賴 Codex report。

## 2. 實際修改查驗

- notify cron deploy target 改用 `grep -vE` 排除 `CHANNEL_ACCESS_TOKEN` 與 `CHANNEL_SECRET`，不再把兩者複製進 build context 的 `.env.yaml`。
- notify cron Cloud Run deploy command 保留既有資料庫密碼 binding，新增 `CHANNEL_ACCESS_TOKEN=CHANNEL_ACCESS_TOKEN:1` runtime binding。
- `--no-allow-unauthenticated` 保持不變。
- 新增 `.dockerignore`，排除 `.env.yaml`、Python cache、tests 與本機 artifacts；保留 Dockerfile 需要的 `dist/`。
- 新增 4 個 standard-library-only deployment contract tests。
- Python 3.10 workflow 新增 notify cron suite，未增加 secrets、write permission、dependency install、deploy 或 publish 行為。
- 沒有修改 application code、requirements、database model/schema 或其他服務 deployment config。

## 3. 驗收條件逐項結果

| 驗收條件 | 結果 | 證據 |
| --- | --- | --- |
| LINE credentials 不進入 build env file | 通過 | notify cron deploy target 同時排除 access token 與 channel secret。 |
| Runtime 綁定既有 LINE token Secret | 通過 | Cloud Build command 包含 `CHANNEL_ACCESS_TOKEN=CHANNEL_ACCESS_TOKEN:1`。 |
| 保留資料庫 Secret binding | 通過 | `DSN_PASSWORD=supabase-database-password:latest` 未被移除。 |
| Cloud Run 維持 private | 通過 | 保留 `--no-allow-unauthenticated`，沒有 public flag。 |
| Docker build context 排除 `.env.yaml` | 通過 | 新增 `.dockerignore` 並明確列出 `.env.yaml`。 |
| 新增離線部署契約測試 | 通過 | 4 tests 只讀 repository deployment text，不讀取真實環境檔。 |
| 四項安全退化可被捕捉 | 通過 | Work 以 in-memory mutation 驗證 token binding、credential filter、Docker ignore 與 private boundary 均被測試捕捉。 |
| 既有 game broadcast suite | 通過 | 本機 Python 3.12.13 執行 17/17 通過。 |
| notify cron suite | 通過 | 本機 Python 3.12.13 執行 4/4 通過。 |
| Python 3.10 CI | 通過 | PR #26 run `30917149772` 使用 Python 3.10.20，17 tests 與 4 tests 均為 `OK`。 |
| Workflow 安全邊界 | 通過 | 仍為 `contents: read`；沒有 secret、write、GCP、deploy 或 publish step。 |
| Git diff 與任務範圍 | 通過 | `git diff --check` 無錯；implementation diff 限於規格指定檔案。 |
| Codex report | 通過 | 包含修改、命令、測試、未測事項、安全聲明、假設與 blocker。 |

## 4. Work 獨立測試證據

### 本機 tests

```text
Python 3.12.13
game_broadcast_service: Ran 17 tests — OK
notify_cronjob_service: Ran 4 tests — OK
```

### Mutation checks

Work 在記憶體內分別模擬：

- 移除 `CHANNEL_ACCESS_TOKEN` runtime binding。
- credential filter 不再排除 `CHANNEL_SECRET`。
- `.dockerignore` 移除 `.env.yaml`。
- private flag 改為 public。

四種 mutation 均使對應 contract test 失敗。前兩次 mutation helper 因 PowerShell 引號解析而未執行測試；修正 helper 後四項檢查成功完成。這不影響兩個 repository test suites 的通過結果。

### GitHub Actions

- Run：`30917149772`
- Job：`92018055810` / `Python 3.10 unittest suite`
- Conclusion：`SUCCESS`
- Python：`3.10.20`
- game broadcast：`Ran 17 tests in 0.018s`、`OK`
- notify cron：`Ran 4 tests in 0.002s`、`OK`

## 5. 原 PR blocker 處理

Codex 的 `blocked` 並非 implementation 或 CI 問題，而是其 session 找不到新安裝的 GitHub CLI，且瀏覽器受 sandbox 限制。Work 使用已安裝的 GitHub CLI 建立 Draft PR #26，blocker 已解除；PR 與 CI 均成功。

## 6. 回歸風險

- 靜態測試與 CI 不能證明 Secret version 1 已 enabled、內容正確或 Cloud Run service account 具 accessor IAM。
- 尚未執行 Docker build、Cloud Build、image layer scan、Cloud Run deployment 或 staging smoke test。
- `.env.yaml` 仍會作為非敏感 runtime environment file 上傳至 Cloud Build；credential filter 與 `.dockerignore` 共同保護 LINE credentials 與 image boundary。
- 文字式 contract tests 對部署命令格式變更有一定敏感度，未來重排 Makefile/Cloud Build 時需同步維護。
- 本機憑證曾在先前工具輸出中短暫出現；是否輪替仍為 Owner 的獨立決策。

## 7. Blocking 問題

無。

## 8. 非阻擋建議

- merge 前保留 Draft PR，待本次 Work review 文件 push 後的最終 CI 再次成功。
- 日後若要驗證線上整合，應另立受控部署／inventory 任務，不應在本 PR 操作 Secret 或部署。
- web portal 與 line webhook 的 Secret 傳遞應分開立案，避免擴張 TASK-003。

## 9. 驗收結論

`accepted`

TASK-003 已符合 repository-only Secret boundary、離線回歸測試與 Python 3.10 CI 要求，沒有 blocking issue。建議在 Work review commit 的最終 CI 通過後交由 Owner 決定是否將 PR #26 標記 ready 並 merge。此結論不批准部署、Secret 操作、憑證輪替、正式通知或不可逆資料操作。

## 10. Owner 決策與合併結果

- Owner 已於 2026-08-04 接受 TASK-003 驗收結論，並授權將 PR #26 標記 ready 及 merge。
- Work review push 後的最終 Actions run `30917468698` 成功。
- PR #26 已合併，merge commit 為 `9b812f5c476d804b434e484ea7f4e8bfd299bfa4`。
- Merge commit title：`security(notify-cron): keep LINE credentials out of images`。
- 沒有部署、Secret 操作、憑證輪替、正式通知或不可逆資料操作。
