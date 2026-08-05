# 專案狀態

更新時間：2026-08-05T13:23:00+08:00
維護角色：Work
證據基準：`main` merge commit `b14dcad3d1261772c8dc00898ba1caca114ce941`

## 1. 目前摘要

- 系統整合球隊賽程、成員、出席回覆、LINE webhook/通知、Discord 管理通知與網站顯示。
- 最近完成的 P0 工作集中在 `game-broadcast-service` 的氣象 API 與 LINE access token 安全邊界。
- P0 程式與部署設定已提交，但尚未部署、尚未驗證 Cloud Build/Cloud Run/Secret Manager，也沒有發送真實 LINE 或 Discord 訊息。
- 第一份正式任務 `TASK-001` 已由 Codex 完成、Work 驗收為 `accepted`，由 Owner 接受，並提交於 `6d2dad0`。
- `TASK-002` 已由 Codex 完成、Work 驗收為 `accepted`，並由 Owner 接受結案。
- PR #25 已合併；Work 已獨立確認 Python 3.10 GitHub Actions run 成功，17/17 tests 通過。
- Owner 已批准 Draft PR 一次授權流程；未來一般任務可一次授權 branch、commit、push、Draft PR、CI 查驗及同一 PR 內的驗收證據更新，merge 仍由 Owner 最終決定。
- TASK-003 已由 Codex 實作、Work 驗收為 `accepted`，並由 Owner 透過 PR #26 合併；merge commit 為 `9b812f5`。
- Owner 已批准描述性 commit/PR title 規範；TASK 編號只放在 body/footer，不再作為標題主體。
- Owner已持續授權Work／Codex在完成範圍內工作並通過驗證後自行建立local commits；push、PR、部署及其他外部／高風險操作仍須依既有閘門另行授權。
- TASK-004 已由 Codex 完成、Work 驗收為 `accepted`，並由 Owner 透過 PR #28 合併；merge commit 為 `c70ce63`。
- Owner 已採用任務 commit 精簡規則：原則上每個任務保留功能、Codex 完工與 Work 驗收三類 commit，純 merge closeout 併入下一個規劃 commit。
- TASK-005 已由 Codex 完成、Work 驗收為 `accepted`，並由 Owner 透過 PR #29 合併；merge commit 為 `086d663`。
- TASK-006 production deployment runbook 已由 Owner 接受為標準流程；採納不等於任何實際部署授權。
- Web Portal 因完整 `.env.yaml` 進入 build context且缺少 `.dockerignore`，在 Secret/build boundary 修正前列為禁止部署。
- Production 唯讀 inventory 曾確認三個服務各缺一批已合併修正；Owner 後續逐項批准，現已全部完成部署。
- TASK-008 已完成：game broadcast revision `00030-pgg` ready／healthy 並承接 100% traffic；TASK-005 已部署，未人工觸發通知且未 rollback。
- TASK-009 已完成：notify cron revision `00010-z2x` ready／healthy並承接 100% traffic；LINE token 已改用 runtime Secret reference，未人工觸發通知且未 rollback。
- TASK-011 已完成唯讀 Gen2 rollback 準備；old source generation 與官方 v2 PATCH recovery path 已確認，未下載 source 或修改 production。
- TASK-010 已完成：commit `086d663` 已部署至 update schedule revision `00028-bij`；build 與平台健康驗證通過，未人工 invoke且未觸發 rollback。
- TASK-012 mobile-first Web Portal local demo MVP已完成並由Owner local視覺驗收接受：雙重development gate、session-only虛構資料、Dashboard／賽程／詳情／個人／等待核可及10項離線測試完成；未部署。
- TASK-013已由Owner接受並透過PR #30合併；merge commit為`9744331`。
- TASK-014已依Owner精確批准執行：revision `game-broadcast-service-00031-s65`建置與部署成功，但唯一一次authenticated `GET /healthz`回傳404，已依trigger將100% traffic rollback至Ready的`00030-pgg`。Service維持private，Scheduler未變。
- TASK-015已完成bounded diagnosis：build source與deployed image的health route正確，但精確時間窗沒有container request log，故404發生於Cloud Run frontend／container之前；尚待Owner決定是否查詢極窄Cloud Audit HttpIngress policy logs。
- TASK-015後續Cloud Audit `HttpIngress` policy metadata精確查詢亦為0筆，沒有證據支持可記錄的policy denial；URL／frontend routing仍待另一次獨立批准驗證。
- TASK-016已由Owner接受並透過PR #32合併；merge commit為`b14dcad3`。兩個排程服務不再於import-time查詢LINE groups，notify package亦不再於import-time執行`announce('Hi')`；尚未部署至production。
- TASK-017已完成：main commit `b14dcad3`部署至production notify cron revision `00011-jpj`，Ready／healthy並承接100% traffic；未人工invoke或觸發rollback。
- TASK-018已完成：main commit `b14dcad3`的game broadcast image以精確digest部署至revision `00033-mdp`，Ready／healthy並承接100% traffic；固定`:tag1`曾使原deploy step no-op，應另立工具鏈修正。

## 2. 已確認事實

### 2.1 最近完成工作

依 branch 名稱與連續 commit，P0 範圍目前暫定為：

1. `0521a02 fix: move weather API key to Secret Manager`
2. `9d99cfb fix: add .dockerignore`
3. `f1884bf fix: bind LINE token from Secret Manager`

已確認的結果：

- 氣象 API key 不再直接存在目前的 `game_reminder.py`。
- `WEATHER_API_KEY` 與 `CHANNEL_ACCESS_TOKEN` 由 `game-broadcast-service` 的 Cloud Run 部署設定綁定 Secret Manager。
- 部署前產生一般環境檔時會排除 `CHANNEL_ACCESS_TOKEN` 與 `CHANNEL_SECRET`。
- `.dockerignore` 排除 `.env.yaml`、Python cache 與 tests。
- 氣象 API 失敗時可降級為不含氣象資訊的基本賽事提醒。
- P0 沒有 database model、schema 或 migration 變更。
- 最新 commit `f1884bf` 只修改：
  - `apps/game_broadcast_service/cloudbuild.yaml`
  - `makes/deploy_apps.mk`

### 2.2 目前元件

| 元件 | 已確認責任 | 部署邊界 | 主要依賴 |
| --- | --- | --- | --- |
| `apps/web_portal` | LINE Login、出席查詢、未來賽程、比賽名單、LINE user/member 配對 | Cloud Run；部署設定為 public | PostgreSQL、LINE Login API、Discord |
| `apps/game_broadcast_service` | 邀請、取消與賽前提醒；可附氣象 | Cloud Run；應維持 private | PostgreSQL、LINE Messaging API、中央氣象署 API、Discord |
| `apps/notify_cronjob_service` | 未來賽程公告與出席統計 | Cloud Run；應維持 private | crawler API、PostgreSQL、LINE Messaging API、Discord |
| `functions/line_webhook_handler` | LINE signature 驗證、使用者事件、出席 postback | Cloud Functions Gen2；HTTP public，應用層驗證 signature | PostgreSQL、LINE Messaging API、Discord |
| `functions/update_game_schedule` | 取得賽程並新增/標記取消 | Cloud Functions Gen2；應維持 private | crawler API、PostgreSQL、Discord |
| `shared_lib/shared_module` | SQLAlchemy models、通知 client、訊息模板、出席分析與共用設定 | source distribution `shared_lib-0.0.1.tar.gz` | 所有 apps/functions |

### 2.3 資料與部署

- 程式使用 PostgreSQL，主要 schema 為 `ntubtob`。
- 可見 models 包含 `games`、`members`、`line_users`、`game_attendance_replies`、`line_groups`、`ballparks`、`discord_webhooks` 與舊的 `line_notify_tokens`。
- Repository 沒有正式 migration framework 或可重建 schema 演進歷史的 migration 檔。
- Makefiles 指定 GCP project `ntubtob-schedule-405614`、region `asia-east1`。
- Cloud Run apps 透過 Cloud Build 建置並推送到 Artifact Registry；目前使用固定 image tag `tag1`。
- 真實 `.env.yaml` 依 `AGENTS.md` 視為敏感資料，本次狀態整理未讀取其內容，只以 `.env_example.yaml`、程式碼與部署設定判斷所需 key。

## 3. 驗證證據

2026-08-04 已由 Work 執行：

- TASK-001 前：`game_broadcast_service` unittest 13/13 通過。
- TASK-001 驗收：完整 unittest 17/17 通過，包含 4 個部署契約測試。
- Work 以 in-memory mutation 確認缺少 LINE binding、LINE secret filter、`.env.yaml` ignore 或 private flag 時，對應測試都會失敗。
- 測試使用 stub/mock 隔離 HTTP、資料庫與 LINE，沒有外部呼叫。
- `git diff --check`：通過。
- 最新 P0 部署設定的靜態存在性檢查：必要 Secret 綁定、敏感欄位過濾、`.dockerignore` 與 private Cloud Run flag 均存在。
- TASK-002 驗收：完整 unittest 17/17 通過；workflow 的 triggers、唯讀權限、runner、timeout、Python 3.10、test command、完整 action SHA 與禁用項目靜態檢查均通過。
- Work 已由官方 action repository 的 exact commit 與 release page 確認 checkout v7.0.1 與 setup-python v7.0.0 的 SHA。
- PR #25 / Actions run `30912783037`：GitHub parser 接受 workflow，Python 3.10.20 hosted runner 執行 `Ran 17 tests` 並回報 `OK`；job conclusion 為 `SUCCESS`。
- TASK-003 本機驗收：game broadcast 17/17、notify cron 4/4 通過；四項安全 mutation 均被 contract tests 捕捉。
- PR #26 / Actions run `30917149772`：Python 3.10.20 執行兩個 suites，17 tests 與 4 tests 均回報 `OK`；job conclusion 為 `SUCCESS`。
- TASK-004 Work 驗收：本機 schedule 5/5、game broadcast 17/17、notify cron 4/4 通過；原錯誤型 date-only mutation 會錯誤保留非本隊賽事。
- PR #28 / 最新 Actions run `30919277284`：Python 3.10.20 執行三個 suites，17、4、5 tests 全數通過；job conclusion 為 `SUCCESS`，權限維持 `contents: read`。
- TASK-005 Work 驗收：本機 game broadcast 24/24、notify cron 4/4、schedule 5/5 通過；cached/import-time snapshot mutation 會與第二次跨日 request 的正確結果不同。
- PR #29 / 最新 Actions run `30921789436`：Python 3.10.20 執行三個 suites，24、4、5 tests 全數通過；job conclusion 為 `SUCCESS`，權限維持 `contents: read`。
- TASK-014隔離驗證：game broadcast 26/26通過，compile check及shared library build通過。
- TASK-014 Cloud Build `fe74ab5d-7fa8-4ff1-8220-fa914b569f63`成功；revision `00031-s65` Ready且deployment contract未漂移，但唯一一次authenticated health smoke回傳404。
- TASK-014 rollback驗證：`00030-pgg` Ready並承接100% traffic；private IAM及三個Scheduler jobs未漂移。

限制：

- 本機測試環境仍為 Python 3.12.13；Python 3.10.20 已由 GitHub-hosted runner 實跑成功。
- Black 未安裝於可用 Python runtime，尚未執行 formatter check。
- Game broadcast已執行production Docker／Cloud Build、Cloud Run control-plane與Secret reference／IAM查詢；未執行image layer掃描、Cloud Run staging或LINE smoke test。
- `GET /healthz` production smoke回傳404；未讀application logs，根因尚未確認。
- 測試通過不代表線上整合正確。

## 4. 當前工作

| 任務 | 狀態 | 下一位角色 | 目標 |
| --- | --- | --- | --- |
| `TASK-019` | `ready_for_codex` | `codex` | Owner已批准repository-only實作與PR工作包；禁止wrapper execute path及任何production操作。 |

正式任務規格：`docs/coordination/tasks/TASK-016.md`
交接狀態：`docs/coordination/HANDOFF.yaml`

## 5. 優先工作佇列

### P1：安全、資料正確性與 P0 回歸

| 項目 | 使用者價值 | 風險 | 影響範圍與依賴 |
| --- | --- | --- | --- |
| P0 部署契約回歸測試 | 防止漏綁 LINE/Weather Secret、環境檔進入 image 或 private 邊界退化 | 低；文字式設定測試可能對格式敏感 | `TASK-001` 已由 Owner 接受並提交於 `6d2dad0`。 |
| 其餘服務 Secret 傳遞盤點與分段改善 | 降低 LINE、LINE Login、session secret 進入 build/image 的風險 | 高；錯綁會中斷登入、webhook 或通知 | notify cron、web portal、line webhook deploy config；需 Owner 批准 Secret 相關工作與確認版本/IAM。 |
| 已曝光憑證的輪替/撤銷計畫 | 避免歷史值繼續有效 | 高；輪替順序錯誤會中斷服務 | 氣象、LINE Messaging、LINE Login 等；需 Owner 明確批准與 rollback window。 |
| web portal 管理 endpoints 授權 | 防止未授權配對/忽略 LINE user | 高；需避免鎖住合法管理者 | web portal session/auth/routes；需 Owner 定義管理者規則。 |
| schedule team filter 修正與測試 | 避免非本隊賽程進入新增/取消比對 | 高；錯誤賽程可能連鎖通知 | `update_game_schedule`；需匿名化 fixture 與預期隊名案例。 |
| request-time 時間計算 | 避免長壽命 instance 使用啟動時的舊日期 | 中高；時區邊界易出錯 | game broadcast、notify cron；需 Asia/Taipei 邊界測試。 |
| attendance cache invalidation 查證 | LINE 回覆後網站能看到最新資料 | 中；清 cache endpoint 不可任意公開 | shared cache helper、web portal；需確認 cache backend 與授權方式。 |

### P2：可維運性

- 建立 Python 3.10 CI；`TASK-002` 已結案，PR #25 已合併且第一次線上 run 成功。
- 建立 Cloud Scheduler、Cloud Run/Functions、service account 與 revision inventory/runbook；查詢雲端前需 Owner 批准。
- 改用不可變 image tag/digest，改善 commit→image→revision 可追溯性。
- 集中必要環境設定的啟動驗證與安全錯誤訊息。
- 建立 LINE/Discord dry-run 或 fake adapter 測試。
- 修正 README 與實際服務責任不一致之處。
- 在不接觸正式 DB 的前提下，定義 migration、備份與 rollback 流程。

### P3：技術債

- 確認無使用者後清理舊 LINE Notify model/template/import。
- 分服務鎖定 dependencies，改善 build 可重現性。
- 統一外部 HTTP timeout、retry、錯誤分類與 idempotency 策略。
- 在測試與 release 基礎完成後，改善 shared library 封裝與暫存檔流程；目前不建議大型重寫。

## 6. 主要風險與假設

### 已確認風險

- 舊氣象 API key 曾出現在 Git 歷史；從 HEAD 移除不等於已在供應商端撤銷。
- P0 的 Cloud Run Secret version 與 runtime IAM 尚未查證。
- P0 已新增離線部署契約測試、通過 Work 驗收並提交；仍不代表線上 Cloud Build/Run/Secret 整合已驗證。
- Python 3.10 CI 已在線上成功；其範圍仍僅涵蓋目前 17 個離線測試，不能取代 Cloud Build/Run/Secret 或外部整合驗證。
- notify cron 的 repository deployment config 已在 PR #26 修正 build/runtime Secret boundary；尚未以 Docker/Cloud Build/Cloud Run 線上驗證。
- notify cron 的本機 `.env.yaml` 未追蹤、已忽略且無 Git 歷史；其中憑證曾在本機工具輸出短暫出現，是否輪替待 Owner 決定。
- 固定 image tag `tag1` 降低部署可追溯性。
- web portal 的 member 配對管理 routes 未見 authentication/authorization 檢查。
- `update_game_schedule.game_crawl()` 的第二次 filter 曾從原始 `game_list` 開始而丟失 team filter；TASK-004 已修正、驗收並合併，尚未 deploy。
- game broadcast 曾在 module import時計算目前時間；TASK-005 已修正、驗收、合併並部署。Notify cron 未使用的同類 globals 亦已移除並部署。
- cache helper 呼叫的 `/clear-cache/attendance` route 在目前 web portal 程式中未找到。

### 推論

- 私有排程 endpoints 應由 Cloud Scheduler 以 OIDC/IAM 呼叫，但 repository 沒有 job 定義。
- `notify_cronjob_service` 與 `game_broadcast_service` 的正式責任可能部分重疊；需用實際排程 inventory 確認。
- LINE Messaging channel 與 LINE Login channel 應為不同用途，但實際 channel 對應未查雲端。

### 待 Owner 確認

- P0 是否包含 `0521a02`、`9d99cfb`、`f1884bf` 三個 commit，或只指最新 commit。
- 是否批准日後做 GCP/Secret/IAM/排程的唯讀 inventory。
- 是否啟動已曝光憑證的輪替/撤銷計畫。
- web portal 哪些頁面必須公開、哪些只限管理者。
- 哪個服務是賽程公告與提醒的權威來源，避免重複排程或通知。

## 7. 安全與操作限制

除非 Owner 明確批准，不得：

- 部署 production 或建立 Cloud Run/Functions revision。
- 執行 Cloud Build submit。
- 讀取、顯示、複製、建立、輪替或刪除 Secret。
- 發送真實 LINE/Discord 通知。
- 連線或寫入 production DB。
- 修改 Cloud Scheduler、IAM 或正式流量。
- 執行不可逆資料操作、重大架構變更、commit、push、PR 或 merge。

## 8. 文件狀態

- 協作規則：`docs/coordination/COLLABORATION.md`
- 唯一交接來源：`docs/coordination/HANDOFF.yaml`
- 專案狀態：本文件
- 已完成任務：`docs/coordination/tasks/TASK-001.md`、`docs/coordination/tasks/TASK-002.md`、`docs/coordination/tasks/TASK-003.md`
- Codex report：`docs/coordination/reports/TASK-003-CODEX.md`
- Work review：`docs/coordination/reviews/TASK-003-WORK.md`
- Owner 已接受 TASK-001 與 TASK-002 結案；正式紀錄見 `docs/coordination/DECISIONS.md`。
- Draft PR 一次授權流程已記錄為 `DEC-004`，並納入 `COLLABORATION.md` 版本 1.1。
- notify cron 與 game broadcast 共用 LINE 官方帳號的產品規則已記錄為 `DEC-005`。
- TASK-003 與 PR 工作包授權已記錄為 `DEC-006`。
- TASK-003 接受與 merge 已記錄為 `DEC-007`。
- 描述性 commit／PR title 規範已記錄為 `DEC-008`，並納入 `AGENTS.md` 與 `COLLABORATION.md` 版本 1.2。
- TASK-004 與 PR 工作包授權已記錄為 `DEC-009`。
- TASK-004 接受與 merge 已記錄為 `DEC-010`。
- 任務 commit 精簡規則已記錄為 `DEC-011`，並納入 `COLLABORATION.md` 版本 1.3。
- TASK-005 與 PR 工作包授權已記錄為 `DEC-012`；規格為 `docs/coordination/tasks/TASK-005.md`。
- TASK-005 Codex report：`docs/coordination/reports/TASK-005-CODEX.md`。
- TASK-005 Work review：`docs/coordination/reviews/TASK-005-WORK.md`。
- TASK-005 接受與 merge 已記錄為 `DEC-013`。
- TASK-006 deployment runbook：`docs/operations/DEPLOYMENT_RUNBOOK.md`。
- Web Portal 產品與風險規劃：`docs/planning/WEB_PORTAL_PLAN.md`。
- TASK-004 Codex report：`docs/coordination/reports/TASK-004-CODEX.md`。
- TASK-004 Work review：`docs/coordination/reviews/TASK-004-WORK.md`。
