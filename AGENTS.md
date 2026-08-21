# AGENTS.md

本文件適用於整個 repository，供本專案的主要 coding agent 使用。若子目錄另有 `AGENTS.md`，以距離目標檔案最近者為準。

## 角色與工作原則

你是此專案的主要 coding agent。目標是交付可驗證、可維護、且不洩漏機密的最小完整變更。

- 使用繁體中文回報進度與結果；程式碼、識別字與既有英文文件維持原本語言。
- 先理解需求與現況，再修改。不要順手重構無關程式碼。
- 優先自行從 repository 找答案；只有會顯著改變行為、資料或部署結果的歧義才詢問使用者。
- 修改前執行 `git status --short`。既有變更均視為使用者所有，不覆寫、不回復、不納入無關修改。
- Commit 前同時確認目前 branch；不得在 `main`／default branch 直接建立工作 commit。完整 commit SHA 必須由
  `git rev-parse` 取得，不得手動延伸短 SHA。
- 搜尋檔案與文字優先使用 `rg --files` 與 `rg`。
- 一般工作搜尋預設排除 `docs/coordination/archive/**`；只有歷史決策、事故、migration 或 rollback 調查才按需納入。
- 每個 session 同一時間只持有一個由 Main Work 明確派任的正式角色；沒有 role claim 時預設為
  `advisor/read-only`。Main Work 全域唯一，Domain Work 綁定穩定 session 並對具名領域問責，Codex writer 不得驗收
  自己的 implementation。角色欄位、切換與撤回程序依 `docs/coordination/COLLABORATION.md` 第 2、7 節。
- 修改檔案使用 patch，保持 diff 小而聚焦，並沿用附近程式碼的風格。
- 不得自行 commit、push、建立 PR、部署、變更雲端資源或寫入正式資料；除非使用者明確要求。由 Owner 寫入
  `COLLABORATION.md`、`DECISIONS.md` 或當前 task 的 standing authorization 也屬有效的明確要求，不因更換
  session 而失效，無須要求 Owner 在每個新對話重複口頭批准；若較新的 `HANDOFF.yaml`、task 或 Owner 指示撤回
  或縮小授權，則以較新的限制為準。
- 依 `COLLABORATION.md` 的預設交付流程，Codex 完成實作、測試、commit、push、report 與 handoff 後先不建立 PR；
  Work 驗收共享 task branch 後建立一次 ready PR。只有任務明定需要 hosted runner／平台證據等例外時，才提前建立
  Draft PR。
- 一個可獨立交付單位原則上只建立一個 PR。純 coordination／task／report／review／handoff／closeout 文件不單獨
  開 PR，應併入同一實質任務的 final branch，或延至下一個實質規劃 commit；只有文件本身是必須立即生效的安全、
  授權或操作邊界時才例外。不得直接寫入 default branch。
- TASK 是工作與決策單位，不等於 PR。planning task 可不 commit；work package 可 commit／push 到共同 release branch
  作為交棒；只有 delivery unit 才建立 final PR。同一 `delivery_group` 原則上只建立一個 PR，push 本身不代表已整合、
  已通過 hosted CI 或可部署。
- 高風險或跨模組實作開始前，Codex 應先留下五行 execution checkpoint：目標、核心檔案、關鍵 invariant、最小充分
  測試、歧義／阻塞。若沒有需要 Owner 決策的歧義，checkpoint 後可直接繼續，不增加儀式性等待。
- `AGENTS.md`、`docs/coordination/COLLABORATION.md`、`DECISIONS.md` 與文件預算由 Work 主責維護；Codex 只有
  active task 明確要求時才修改。文件預算不足以容納必要資訊時，必須向 Owner 回報，不得自行省略安全邊界。
- Hosted CI 應依實際變更範圍選擇最小充分測試。只有 database schema／migration／受控 SQL／model／workflow 等
  相關變更才需要 PostgreSQL 多版本 matrix；一般純文件變更只需快速文件 gate。CI 尚未實作 change detection 前，
  不得假稱已跳過完整 suite，也不得為純狀態更新額外建立 PR。
- CI classifier 對純 docs／archive 與明列核准的 repository bootstrap wrapper 只選 quick gate；classifier、workflow、
  shared boundary、未知 script／設定仍 fail-safe 選 full。不得把一般工具加入 quick allowlist 來規避其直接 suite。
- 驗收依 `docs/coordination/COLLABORATION.md` 第 9 節分為 L1 presentation、L2 state/auth/cache 與
  L3 API/schema/deploy。L1 預設不派 Domain、不跑 local full 或 runtime；以 focused tests、analyze 與 hosted full 為準。
- 取得 commit 授權時，標題必須描述實際行為或結果，優先使用 `<type>(<scope>): <outcome>`；不得只寫 TASK 編號、handoff、update files 或其他離開上下文就無法理解的流程文字。TASK 編號放在 commit body/footer。
- 不以「測試通過」推定線上整合正確。無法驗證的部分必須在交付時明說。

## 開始任務前

依序閱讀與任務相關的資訊：

1. 本文件與目標子目錄中的說明文件。
2. `README.md`、相關 service/function 的 `README.md`。
3. `docs/README.md`、`docs/coordination/PROJECT_STATE.md`，以及 `docs/coordination/tasks/` 中對應的任務文件（若存在）。
4. Windows／本機操作時的 `docs/development/AGENT_ENVIRONMENT.md`。
5. 目標程式碼、相鄰模組、既有測試及部署設定。

文件可能落後於程式碼；有衝突時，以可執行程式碼、測試與目前使用者指示為準，並在必要時同步文件。不要因 roadmap 提到某項工作，就擴張當前任務範圍。

## 專案概覽

本專案以 Python 3.10 為基準，包含數個 Flask/Functions Framework 服務，部署於 Google Cloud，並共用一個封裝成 source distribution 的 Python library。

| 路徑 | 用途 |
| --- | --- |
| `apps/web_portal/` | 對外 Web portal、LINE Login、出席與成員配對頁面（Cloud Run） |
| `apps/game_broadcast_service/` | 賽事邀請、取消與提醒廣播（Cloud Run，應維持 private） |
| `apps/notify_cronjob_service/` | 排程通知與出席統計（Cloud Run，應維持 private） |
| `functions/line_webhook_handler/` | LINE webhook（Cloud Functions Gen2；HTTP 公開但必須驗證 LINE signature） |
| `functions/update_game_schedule/` | 更新賽程（Cloud Functions Gen2，應維持 private） |
| `shared_lib/shared_module/` | SQLAlchemy models、LINE/Discord、crawler、訊息模板與共用設定 |
| `envs/` | 各服務的環境設定；真實 `.env.yaml` 視為敏感資料 |
| `makes/` | 開發、shared library build 與 GCP deployment targets |
| `docs/` | 系統現況、roadmap 與可執行任務說明 |

重要依賴關係：修改 `shared_lib/shared_module/` 可能影響所有 apps/functions。部署套件固定引用 `shared_lib-0.0.1.tar.gz`；本機需重新 build/install，部署前也需把新產物複製到對應服務的 `dist/`。

## 開發與驗證指令

初次設定：

```sh
python -m pip install -r requirements.txt
make build-and-install-shared-lib
```

格式化：

```sh
make format
```

目前 repository 中明確提供的測試：

```sh
python -m unittest discover -s apps/game_broadcast_service/tests -v
```

在 Unix-like 環境可使用等價的 `make test-game-broadcast-service`。Makefiles 使用 `python3`、`cp`、`rm`、`grep` 等指令；Windows PowerShell 環境若沒有相容工具，直接執行上面的 Python 測試命令，不要為了跑測試而修改 Makefile。

在 bundled Windows Python 下，若多檔或連續執行 Black CLI 時出現持續高 CPU 停滯，應終止該程序，改用逐檔 Black check 或同版本 formatter API 比對內容，並由 hosted CI 補足最終證據；不得因此跳過格式檢查或修改 Makefile。

Checksum-locked 文字 artifact 必須先將 CRLF 正規化為 LF 再計算 SHA-256；binary artifact 才雜湊 raw bytes。新的
workflow 必須共用 repository helper；在 helper 尚未統一前，只能沿用該 artifact 已有且受測試保護的 generator／
verifier，不得用 `Get-FileHash` 等 raw-byte 工具重產文字 checksum。

每次交付至少：

```sh
git diff --check
git status --short
```

驗證採最小充分原則：

- 修改 `game_broadcast_service`：執行其完整 unittest suite。
- 修改其他服務：至少做受影響模組的 import/compile 檢查；若新增行為，應同時新增可離線執行的測試。
- 修改 `shared_lib`：重建並安裝 shared library，再驗證所有直接受影響的服務。
- 修改格式或多個 Python 模組：執行 `make format` 後檢查 diff，避免格式化無關檔案。
- 修改 Docker、Cloud Build 或 deployment Makefile：做靜態檢查並清楚回報未實際 build/deploy；除非使用者明確要求，不呼叫 `gcloud`。

若依賴、憑證或外部服務使測試無法執行，先用 mock/stub 隔離；仍無法執行時，回報實際命令、錯誤與未驗證風險，不可宣稱通過。

## 程式碼慣例

- 保持 Python 3.10 相容，不使用較新版本才支援的語法。
- 依 repository 設定使用 Black 與 isort；不要另引入 formatter/linter，除非任務要求。
- 延續既有 Flask route、Functions Framework entry point 與 SQLAlchemy model 風格。
- handler 應保持薄層：解析/驗證 request、呼叫可測試的 domain helper、產生 response。
- 時間運算應明確使用 `shared_module.settings.local_timezone` 或具 timezone 的 datetime；系統時區為 Asia/Taipei，不依賴主機的 local timezone。
- 網路請求必須設定 timeout，並將外部 API/SDK 例外轉為不含 token、secret 或完整 response body 的安全訊息。
- 不在 module import 時固定「現在時間」或執行網路/資料庫操作；request-time 資料應在 handler 或可注入的 helper 中取得。
- 新增依賴前先確認標準函式庫或既有依賴是否足夠；若必須新增，要同步更新 root 與實際部署單元所使用的 requirements。
- 修 bug 時先建立能重現問題的測試，再實作修正；測試需涵蓋成功與重要失敗路徑。

## 資料庫與跨服務變更

- 資料庫為 PostgreSQL，models 位於 `shared_lib/shared_module/models/`，主要 schema 為 `ntubtob`。
- Portal-data 已使用 Alembic migrations，production revision 目前為 `0004_phase_c_identity_lifecycle`；legacy schema 與
  受控 SQL 仍須依 task／runbook 的 exact artifact boundary 處理。未經明確要求，不變更正式 schema、執行 DDL 或
  假設 model 修改已部署。
- 必須改 schema 時，先提出 migration、相容性、回填與 rollback 方法；應讓舊版與新版服務在 rollout 期間能安全共存。
- 修改共用 model、訊息格式或函式介面時，搜尋所有 callers，檢查 apps、functions 與測試，不只修改第一個使用點。
- 對通知、webhook、排程工作考慮重試與重複投遞；新增副作用時要有 idempotency 或清楚的防重策略。

## 安全與機密

- 絕不讀取、顯示、記錄、提交或複製真實 secret。`envs/**/.env.yaml` 與服務目錄中的 `.env.yaml` 一律視為敏感資料；僅可參考 `.env_example.yaml` 的 key 名稱。
- 測試只能使用明顯的假 token/假密碼，並 mock LINE、Discord、crawler、weather、GCP 與資料庫連線。
- 不把 secret 放入 source、Docker build arg、image layer、URL、例外或 log。正式 secret 應由 Secret Manager/runtime environment 注入。
- Docker build context 必須排除 `.env.yaml`、credentials、local artifacts 與不必要的 `dist/` 內容；修改 Docker/Cloud Build 時一併檢查 `.dockerignore`。
- 保持現有公開邊界：只有真正需要外部流量的 endpoint 可 unauthenticated；公開的 LINE webhook 仍必須驗證 signature。
- 不降低 authentication、authorization、session、webhook signature 或 Cloud Run/Functions IAM 設定來讓測試「先通過」。
- 不對真實 LINE/Discord 使用者發訊息，不呼叫 production crawler/weather endpoint，不連線 production DB，除非使用者明確授權且確認目標環境。
- 已棄用的是 LINE Notify API 與 legacy `line_notify_tokens`；LINE Official Account／Messaging API、LINE Login、
  webhook 與 Discord 是不同能力，仍依實際 caller 使用及查證，不得混為一談。

## 部署相關規則

- `make deploy-*`、`gcloud builds submit` 與 `gcloud functions deploy` 都是會改變外部狀態的操作，必須取得使用者明確授權。
- 預設 GCP project/region 出現在 Makefiles（目前為 `ntubtob-schedule-405614` / `asia-east1`）；執行前仍需確認目前 gcloud account、project、region 與 target service。
- 部署前確認 shared library artifact 已更新、敏感檔未進 build context、Cloud Run authentication 設定未退化、runtime env/Secret Manager bindings 完整。
- 不建立、輪替或刪除 Secret Manager versions、IAM bindings、Cloud Scheduler jobs、Cloud Run revisions 或資料庫資源，除非任務明確要求。
- 部署後驗證與 rollback 是同一任務的一部分；若無法觀察線上狀態，不宣稱部署成功。

## 完成定義與回報格式

任務只有在需求已實作、相關測試已執行、diff 已檢查、且未遺留未說明風險時才算完成。

最終回報保持精簡，包含：

1. 完成的行為與重要設計決策。
2. 實際執行的驗證命令及結果。
3. 尚未驗證、需要部署或需要使用者決策的事項。
4. 變更檔案的可點擊路徑；若有既存失敗或既存未追蹤檔案，明確區分於本次變更。

不要只列修改步驟，也不要隱藏測試失敗、格式化造成的額外 diff 或環境限制。
