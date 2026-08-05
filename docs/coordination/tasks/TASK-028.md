# TASK-028：Web Portal Cross-platform Safe Deployment Wrapper

狀態：`awaiting_owner_approval`
優先級：P2 operational safety / developer experience
規劃者：Work
執行者：Codex
Base commit：`d48a5ba`

## 1. 任務目標

建立 Python 3.10 相容、Windows 與 Linux 都可使用的 Web Portal deployment wrapper，消除對 Unix `make/sh/grep/cp/rm` 的必要依賴，並將 TASK-027 實際遇到的 build context、PowerShell substitutions、長時間前景等待、臨時環境檔清理與部署後驗證風險轉成可離線測試的 fail-closed 契約。

本任務只實作與測試工具，不執行 `--execute`、不呼叫 GCP、不部署 production。

## 2. 使用者價值

- Windows 可用一條 Python 指令完成一致的 dry-run preflight。
- production deployment 不再依賴 shell 對逗號、路徑或引號的解讀。
- Cloud Build 可非同步提交並由工具輪詢，不必長時間占用互動主流程。
- 固定正確的 `apps/web_portal` build context，避免提交錯誤目錄。
- 敏感設定不進 image、不出現在輸出，temporary env 無論成功或失敗都清除。
- 部署結果可產生結構化、不含秘密值的驗證摘要，方便交給獨立子流程監看。

## 3. 已確認事實

- 現有 `tools/deploy_scheduled_service.py` 已提供排程服務的跨平台 fail-closed 模式與 mockable runner，可作為設計參考，但目前不支援公開 Web Portal、兩個額外 Secret refs 或 HTTP fail-closed checks。
- Web Portal deployment contract 位於 `apps/web_portal/cloudbuild.yaml` 與 `makes/deploy_apps.mk`。
- 必須排除 temporary env 中的 `DSN_PASSWORD`、`LINE_LOGIN_CHANNEL_SECRET`、`SECRET_KEY`。
- production demo mode 必須保持關閉；部署後允許的最小驗證為一次 `GET /` 期待 200、一次 `GET /demo/` 期待 404。
- TASK-027 曾因 PowerShell 拆分 comma-separated substitutions 使 Cloud Build step 0 失敗，且前景等待曾被本機執行時間上限中斷。

## 4. 範圍

### 4.1 CLI 與 fail-closed gate

- 新增 `tools/deploy_web_portal.py`，或在不破壞既有 CLI 的前提下採同等清楚的模組切分。
- 預設不接受 execution-only arguments、不呼叫 `gcloud`、不做 HTTP request，只執行 repository-local preflight。
- `--execute` 必須同時要求：
  - exact 40-character approved commit；
  - valid `web-portal-*` rollback revision；
  - LINE Login Secret `resource:version` reference；
  - Session Secret `resource:version` reference。
- project、region、service 與 build context 必須固定為 repository 已確認值；不得接受任意 service 或任意 context。
- working tree 非乾淨、HEAD 不等於 approved commit、temporary `.env.yaml` 已存在、所需檔案／工具缺少時必須在任何 cloud mutation 前停止。

### 4.2 Build preparation

- 使用目前 Python interpreter 建立 shared library sdist 並複製到 Web Portal `dist/`。
- 從 `envs/web_portal/.env.yaml` 產生 temporary deployment env，但不得將三個 secret keys 複製進去。
- 不得輸出 source env 內容、管理者 ID 值或 Secret payload。
- 所有成功、失敗與 exception paths 都必須清除 temporary `apps/web_portal/.env.yaml`，且不可覆寫任務開始前已存在的檔案。

### 4.3 Cloud Build orchestration

- 以 argument list 呼叫 subprocess，不透過 shell command string。
- `--substitutions` 必須是單一 argument，涵蓋 service、region、approved image tag 與兩個 Secret refs。
- 明確以 `apps/web_portal` 作為 cwd/context。
- 優先使用 asynchronous Cloud Build submission，解析 build ID 後以 bounded polling 查詢終態。
- polling 必須有 timeout、可測試的 interval／clock injection 或等價設計；不得無限等待或 busy loop。
- 只有 Cloud Build 明確 `SUCCESS` 才可進入部署後驗證；failure、cancelled、expired、timeout 或 malformed response 均安全失敗。

### 4.4 Deployment verification and rollback contract

- 驗證新 revision Ready、approved immutable image digest、100% traffic、public invoker boundary、runtime identity 與預期 runtime key classifications。
- 只比較 Secret resource/version metadata，不讀取 Secret payload，不輸出 plain env values。
- 成功後各執行一次無認證 `GET /` 與 `GET /demo/`，使用標準函式庫或既有 dependency、明確 timeout、禁止 redirect 掩蓋結果；分別要求 200 與 404。
- HTTP check 不得讀取或保存 response body。
- rollback 僅能導向 CLI 明確提供且已通過 service-prefix 驗證的 revision；不得刪除新 revision、image 或 Secret。
- 自動 rollback 的精確觸發點必須有測試，且工具輸出要區分 deployment failure、rollback success 與 rollback failure。
- 成功輸出只包含 build ID、revision、image tag/digest、HTTP status、rollback 是否執行等安全欄位，不包含環境值或 Secret payload。

### 4.5 文件與相容性

- README 補上 Windows／Unix dry-run 指令，以及 production `--execute` 必須依 deployment runbook 與 Owner exact approval 的警告。
- 不移除或破壞 `tools/deploy_scheduled_service.py` 現有 CLI 與測試。
- 可抽取少量共用 pure helpers，但不得藉機全面重寫排程服務 deployment wrapper。

## 5. 非目標與禁止事項

- 不執行 wrapper 的 `--execute` path。
- 不呼叫 production、Cloud Build、Cloud Run、Artifact Registry、Secret Manager 或 HTTP endpoint。
- 不讀取、顯示、複製或提交 `envs/**/.env.yaml` 的真實值；測試只使用明顯虛構 fixture。
- 不部署、不 rollback、不修改 IAM、Secret、Scheduler、Cloud Run 或 repository settings。
- 不測 LINE Login/callback、不連 production DB、不發 LINE/Discord 通知。
- 不修改 application routes、templates、shared models、schema 或 production data。
- 不引入第三方 dependency；優先使用 Python 3.10 標準函式庫。
- 不 push、不建立 PR、不 merge；本輪可依既有 Owner 授權建立描述性 local commit。

## 6. 測試要求

新增可離線執行的 unit tests，所有 subprocess、時間等待與 HTTP 都必須 fake/mock，至少覆蓋：

- dry-run 完全不呼叫 `gcloud` 或 HTTP；
- dirty tree、HEAD mismatch、invalid commit/revision/Secret ref、缺檔與 existing temp env fail closed；
- build context 固定為 `apps/web_portal`；
- substitutions 保持單一 subprocess argument；
- secret keys 被過濾，非敏感 key 保留，內容不出現在 log/result；
- shared artifact build/copy 契約；
- async build ID parsing、working→success、failure、malformed status 與 bounded timeout；
- new revision/digest/traffic/public boundary/runtime identity/Secret classifications 驗證；
- `/` 只 GET 一次且要求 200，`/demo/` 只 GET 一次且要求 404，無 redirect、無 body 保存；
- 每個成功與重要失敗路徑都清除 temp env；
- rollback 未觸發、成功與失敗三種結果；
- 既有 scheduled-service wrapper tests 保持通過。

## 7. 驗收條件

- Windows 可直接執行 dry-run，不需要 Unix make/sh。
- dry-run 預設安全，沒有任何外部網路或 cloud mutation。
- `--execute` 缺少任一 exact approval input 時，在 mutation 前拒絕。
- TASK-027 發生過的錯誤（錯誤 build context、拆分 substitutions、前景 timeout、temp env 殘留）均有 regression test。
- 所有敏感欄位只以 key/reference classification 處理，沒有 value disclosure。
- Python 3.10 CI 可完整執行新增測試，Windows 不再因本工具需要 Unix make/sh 而跳過核心契約。
- README、Codex report、PROJECT_STATE 與 HANDOFF 按協作流程更新。

## 8. 驗證命令

```powershell
python -m unittest discover -s tools/tests -v
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q tools apps/web_portal
python tools/deploy_web_portal.py
git diff --check
git status --short
```

最後一條 CLI 只能跑 dry-run；不得加入 `--execute`。

## 9. 交付文件

- `docs/coordination/reports/TASK-028-CODEX.md`
- 更新 `docs/coordination/PROJECT_STATE.md`
- 更新 `docs/coordination/HANDOFF.yaml` 為 `ready_for_review / work`
- 報告需列出實際命令、測試數量、skip/failure、所有變更檔案、未驗證風險，以及確認沒有 cloud/HTTP/Secret/DB/notification mutation。

## 10. 交棒

Owner 已批准建立 TASK-028 並交棒給 Codex。本輪允許依上述範圍修改程式、測試與文件，並依既有授權建立描述性 local commit；不包含 push、PR、merge 或任何 production execution。

Owner 後續已批准 push 與 PR 工作包：允許 push task branch、建立 Draft PR、唯讀查驗 CI，並在同一 PR 更新驗收證據；仍不包含 merge 或任何 production execution。
