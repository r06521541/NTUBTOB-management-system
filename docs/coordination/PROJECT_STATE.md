# 專案狀態

更新時間：2026-08-06T06:10:00+08:00
維護角色：Work
證據基準：PR #38 squash merge `196c2087a1bfdf816f16aafc267c7008aa376f41`

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
- TASK-019已由Owner接受並透過PR #33合併；merge commit為`b053fce6`。兩個排程服務改用Git SHA image tag，並新增預設只做preflight、fail-closed的跨平台deployment wrapper；尚未以wrapper execute path進行production部署。
- TASK-020已由Codex完成、Work驗收為`accepted`並由Owner透過PR #34合併；缺少／空白／無效LINE signature明確回400且不觸發外部副作用，production／local入口共用同一boundary；merge commit為`c022d518`，尚未部署Cloud Function。
- TASK-021已由Codex完成、Work驗收為`accepted`並由Owner透過PR #35合併；Web Portal成員配對管理端點已有fail-closed Member ID allowlist、LINE session guard與CSRF；merge commit為`a7f801b4`，尚未部署或設定production allowlist。
- TASK-022第二輪Work驗收為`accepted`並由Owner透過PR #36合併：Web Portal temporary env cleanup已具cwd穩定性，畸形Secret references在Cloud Build前fail closed，runtime Secret binding、Docker排除與immutable tag contracts通過；merge commit為`f7471da1`，尚未build、deploy或查驗production Secret／IAM。
- TASK-023 production唯讀盤點完成：`web-portal-00026-rtc` Ready並承接100% traffic、service public、callback host一致且runtime identity具Secret accessor；但LINE Login channel secret與Flask session key仍是plain env，project內沒有可安全唯一辨識的兩個Secret resources，因此Web Portal deployment仍blocked。
- TASK-024第二輪Work驗收為`accepted`並由Owner接受：跨賽事state隔離、交通、通知偏好、月曆／主客場filter、僅觀賽／ETA與Dashboard待辦均已補正；33項tests通過、2項Windows platform skips，尚未做browser visual與Python 3.10實跑。
- Owner提出多元活動方向：幹部可建立聚餐、旅遊、友誼賽／OB賽，且一次Event可包含多場比賽與其他行程；初步方向記錄於`docs/planning/EVENT_MANAGEMENT_PLAN.md`，尚未決定schema或migration。
- TASK-025已由Owner批准並交棒Codex：以session-only demo驗證Event／Activity、幹部builder、聯盟／手動比賽來源、草稿／發布與兩層出席，不碰正式schema或production。
- TASK-025已由Owner正式接受並透過PR #37合併；merge commit為`cdb67bf`，最新Python 3.10 run `31022009347`成功。Demo仍預設關閉，尚未部署Web Portal。
- TASK-026已完成：`web-portal-line-login-channel-secret:1`與`web-portal-session-secret-key:1`均enabled，runtime accessor已確認；未讀回payload、未修改IAM或部署。Web Portal仍需另案部署，且首次使用新Session Secret會使既有登入session失效。
- TASK-027由Work提出：部署merged／CI-passed `cdb67bf`至production Web Portal，使用兩個exact Secret refs與Owner已設定的admin env，含無副作用首頁／demo fail-closed GET及rollback至`web-portal-00026-rtc`；等待Owner精確批准。
- TASK-027 已依 Owner 核准完成：revision `web-portal-00027-fwf` Ready 且承接 100% traffic；首頁 200、production demo 404，未觸發 rollback。
- TASK-028 已由 Owner 接受並以 PR #38 squash merge：`main` 僅新增描述性 commit `196c208`；最終 Python 3.10.20 CI run `31028391679`／job `92382569298` 成功，未執行 production wrapper。
- TASK-029 初版 transferable signed state 已退回並完成安全補正；Owner 選擇 original-browser 路線。Codex 依 LINE 官方建議加入 `disable_auto_login=true`，避免 mobile external browser auto-login app handoff，同時保留 session nonce binding；Work 已驗收為 `accepted`，等待 Owner 決定 push／PR。
- 普通隊員、幹部與系統管理者的初步權限矩陣已記錄於 `docs/planning/ROLE_ACCESS_PROPOSAL.md`，目前僅為未核准提案，不代表 schema 或 migration 決策。
- TASK-039已完成：PR #47 merge為`7082afd`並部署`web-portal-00035-mcl`；登入入口移除自動跳轉，改為一般LINE登入與明確browser fallback，後續實機限制由TASK-040收斂。
- TASK-040已完成：PR #48 merge為`5e85ea9`，手機登入引導改為回到LINE內開啟，電腦保留瀏覽器／QR Code登入；production `web-portal-00036-2p2` Ready並承接100% traffic，公開頁面驗證通過且未觸發rollback。

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

- `TASK-029` 已由 PR #39 squash merge為 `6765448`，Python 3.10 CI成功；尚未部署或以真實瀏覽器驗證。
- `TASK-030` 已建立production rollout與Owner手動LINE Login smoke-test工作包，等待Owner對exact commit、rollback與真實LINE API／production唯讀Member查詢做精確批准。
- `TASK-030` 首次執行在Cloud Build前因Windows無法由Python啟動硬編碼的`gcloud`而安全停止；沒有新build／revision，traffic仍為`web-portal-00027-fwf=100%`。Owner已批准TASK-031修正wrapper executable resolution及PR工作包，TASK-030待其merge後更新exact source再續行。

| 任務 | 狀態 | 下一位角色 | 目標 |
| --- | --- | --- | --- |
| `TASK-031` | `awaiting_owner_approval` | `owner` | Work已驗收接受；決定是否將PR #40標記ready並squash merge。 |
| `TASK-032` | `awaiting_owner_approval` | `owner` | Work已驗收接受；決定是否批准push、Draft PR與Python 3.10 CI查驗。 |
| `TASK-033` | `awaiting_owner_approval` | `owner` | Work已驗收接受；決定是否批准push、Draft PR與Python 3.10 CI查驗。 |
| `TASK-034` | `completed` | `owner` | PR #43已squash merge為`bb91d9e5`；production `web-portal-00032-f7z` Ready並承接100% traffic，無需rollback。 |
| `TASK-035` | `completed` | `owner` | PR #44已squash merge為`5952e0b`；member-only roster guard已在main，尚未部署production。 |
| `TASK-036` | `completed` | `owner` | `5952e0b`已部署為`web-portal-00033-kzq`並承接100% traffic；匿名roster安全回同站登入302，無需rollback。 |
| `TASK-037` | `completed` | `owner` | PR #45的hosted Python 3.10 CI成功並squash merge為`4b9ddd4`；minimal identity session已在main，尚未部署。 |
| `TASK-038` | `completed` | `owner` | PR #46 merge為`d1ebefa`並部署`web-portal-00034-7lm`承接100% traffic；normal login不含`disable_auto_login`，真實UX待Owner驗證。 |
| `TASK-039` | `completed` | `owner` | PR #47 merge為`7082afd`並部署`web-portal-00035-mcl`承接100% traffic；登入選擇頁無自動跳轉且兩個入口存在，真實UX待Owner驗證。 |
| `TASK-040` | `completed` | `owner` | PR #48 merge為`5e85ea9`並部署`web-portal-00036-2p2`承接100% traffic；手機改引導回LINE內開啟，電腦瀏覽器／QR Code登入保留。 |
| `TASK-041` | `completed` | `owner` | 集中role/capability policy已通過Work驗收；production只解析member或allowlist admin且無officer來源，等待與下一項實質成果合併PR。 |

正式任務規格：`docs/coordination/tasks/TASK-029.md`
交接狀態：`docs/coordination/HANDOFF.yaml`

## 5. 優先工作佇列

- 進行中 `TASK-029`：已完成 Owner 選定的 original-browser 路線，保留 session binding並停用 LINE auto-login；等待 Work 驗收，不包含部署或真實登入。

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

### TASK-043 Web Portal深藍／灰品牌介面（2026-08-06）

- 已建立共用品牌與語意色tokens，套用公開首頁、auth/recovery、正式會員頁與Demo；正式會員導覽新增回首頁入口。
- Work要求並確認修正兩項語意問題：瀏覽器theme-color不再使用舊綠；一般warning為暖金，只有明確danger使用紅色。
- Work獨立驗證94項Web Portal測試通過（2項既有Windows make/sh skip）、compile與diff check通過；驗收結論為`accepted`。
- Codex完成375px與desktop本機視覺檢查；Work瀏覽器控制因本機工具路徑問題未能重做截圖驗收。
- 尚未push、建立PR、merge、部署或存取production；TASK-041至TASK-043可合併為單一PR工作包。

### TASK-042 正式帳號頁與安全登出（2026-08-06）

- 已新增 request-time Member 帳號頁、集中 policy 角色標示、capability-aware 管理入口與 POST-only CSRF 登出。
- Work 獨立驗證 89 項 Web Portal 測試通過（2 項既有 Windows make/sh skip）；compile、Python 3.10 grammar 與 diff check 通過。
- 驗收結論為 `accepted`；375px 與桌面視覺驗收併入 TASK-043 品牌介面調整。
- 尚未 push、建立 PR、merge、部署或存取 production。

### TASK-038 safe LINE auto-login fallback（2026-08-06）

- 一般LINE authorization request不再停用auto-login；只有明確`mode=browser`的fallback附加`disable_auto_login=true`。
- State continuity失敗仍在LINE／DB前回400；signed-valid mismatch可保留已驗證站內return path，其他無效state使用固定安全預設。
- Fallback每次建立fresh nonce／signed state，不重用失敗code、state或nonce；未知／ambiguous mode與return input fail closed。
- 71項Web Portal測試通過（2項既有Windows make/sh skip）；compile、Python 3.10 grammar、clean-worktree deployment dry-run與diff check通過。
- 狀態為`ready_for_review / work`；未push、開PR、merge、部署或存取production。

### TASK-037 Web Portal minimal authenticated session（2026-08-06）

- 新LINE callback session只保存opaque `user_id`與`member_id`，不再保存完整Member或LINE display name。
- 舊session在下一次request精確移除兩個legacy欄位，不清除OAuth、CSRF、return path、demo或既有identity。
- Attendance以`member_id`載入fresh Member；Member不存在時清除identity並在Game／attendance／HTTP前fail closed。
- 65項Web Portal測試通過（2項既有Windows make/sh skip）；compile、Python 3.10 grammar、clean-worktree deployment dry-run與diff check通過。
- 狀態為`ready_for_review / work`；未push、開PR、merge、部署或存取production。

### TASK-035 Web Portal member-only roster access（2026-08-06）

- `/game-roster/<game_id>` 已在資料查詢前要求有效 `user_id` 與正整數 `member_id` session，匿名及畸形 session fail closed。
- 合法會員維持既有名單；不存在 game 回覆404且不查attendance。
- Draft PR #44的Python 3.10 CI run `31060596934`成功；未merge、部署或存取production。
- 狀態為`ready_for_review / work`；角色分級RBAC仍維持後續產品決策。

### TASK-034 Web Portal pinned traffic promotion（2026-08-06）

- Codex已把revision contract與traffic convergence拆成兩階段，通過新revision驗證後才顯式promote exact revision至100%。
- promotion前失敗保留舊健康traffic且不做多餘rollback；promotion開始後失敗才依exact approved revision rollback。
- Draft PR #43的Python 3.10.20 CI run `31043954172`成功；tools 41項測試通過（2項platform skip），完整workflow成功。
- 狀態為`ready_for_review / work`；未merge、部署或執行任何production mutation。

### TASK-033 Web Portal rollout convergence polling（2026-08-06）

- Codex已讓deployment wrapper在Cloud Build成功後bounded polling新revision、Ready、核准runtime contract及100% traffic，完成前不執行IAM／HTTP驗證。
- 暫態control-plane收斂會等待；Ready revision的digest、identity、Secret/plain env或demo gate漂移會立即fail closed並rollback。
- 失敗訊息只提供安全stage及rollback結果，不輸出gcloud stderr、env、Secret或HTTP body。
- Tools 38項與Web Portal 58項測試通過（2項既有Windows skip）；compile、Python 3.10 grammar、dry-run與diff check通過。
- 狀態為`ready_for_review / work`；未push、開PR、merge或部署，production仍由`web-portal-00027-fwf`承接traffic。

### TASK-032 Web Portal session cookie migration（2026-08-06）

- Codex 已將 Web Portal session cookie 版本化為 `ntubtob_web_session_v2`，production 明確使用 host-only、Secure、HttpOnly、SameSite=Lax、Path=/。
- 雙重 gate 的 local demo 保留 HTTP session；其他未明確設定環境 fail closed 為 Secure。
- 舊 Flask `session` cookie 會被精確淘汰；無效 LINE state 仍在外部／DB 前回覆 400，只清除 OAuth 暫存並保留既有認證身分，再提供全新登入交易。
- 58 項 Web Portal tests 通過、2 項既有 Windows skip；compile、Python 3.10 grammar、deployment dry-run 與 diff check 通過。
- 狀態為 `ready_for_review / work`；尚未 push、開 PR、merge 或部署。

### TASK-031 Windows gcloud executable resolution（2026-08-06）

- 兩個 deployment wrapper 已在 subprocess 邊界解析 exact executable，使 Windows `gcloud.cmd` 能在 `shell=False` 下安全啟動，並維持 POSIX 相容與 missing-tool fail-closed 行為。
- 34 項 tools tests 與 55 項 Web Portal tests 通過；本機臨時 `.cmd` 的真實離線啟動契約通過，兩個 wrapper dry-run 均未呼叫 cloud。
- 尚待 Work review 與 Hosted Python 3.10 CI；未部署。合併後須重新鎖定 TASK-030 exact deployment commit。

### TASK-027 production deployment closeout（2026-08-06）

- Owner 已批准並完成將 merge commit `cdb67bf007ec67d882c6e974143a4d527f1528cd` 部署至 production `web-portal`。
- Cloud Build `7f155fb7-2288-416a-83a7-d77a95eee7e9` 成功；新 revision `web-portal-00027-fwf` Ready 並承接 100% traffic。
- Production 首頁單次無認證 GET 回應 200；`/demo/` 單次無認證 GET 回應 404，確認 demo mode fail closed。
- DB password、LINE Login channel secret 與 Flask session key 均為 runtime Secret references；Owner 設定的管理者 Member ID allowlist 存在，但 Work 未讀取其值。
- 未測 LINE Login callback、需資料庫的頁面、管理員操作或通知；未修改 IAM、Scheduler、schema 或 production data。
- 完整證據見 `docs/operations/deployments/WEB_PORTAL_CDB67BF.md`。

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
