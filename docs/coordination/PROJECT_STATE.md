# 專案狀態

## 現行協作與 CI 規則

- Owner已批准穩定收斂規則：一個可獨立交付單位原則上只建立一個ready PR；純task／report／review／handoff／
  closeout文件不各自開PR，而是併入同一final branch或下一個實質規劃commit。只有文件本身是必須立即生效的
  安全、授權或操作邊界時才例外。
- Hosted CI應依變更範圍分級：一般純文件走快速gate；單一服務跑受影響suite；database schema／migration／
  model／受控SQL與verifier才跑PostgreSQL 15／16 matrix。現行workflow尚未實作change detection，故這是下一個
  CI實作目標，不代表目前可假稱完整checks已被替代。
- Production批准鎖定material artifacts與reviewed source evidence；純coordination文件或merge metadata不再觸發
  self-referential relock PR。material SQL／checksum／validator／runbook boundary改變仍須fail closed並重新批准。
- 下方關於Draft PR、逐次Owner merge與個別歷史task的敘述是當時事實，不覆蓋目前`COLLABORATION.md`版本1.5
  及較新的standing authorization。

### 舊task相容性盤點（2026-08-08）

- 目前唯一active task為TASK-073；其「任何commit都使批准失效」已修正為material-change gate，reviewed source
  commit與三份SQL checksums維持不變，純coordination文件不再觸發relock。
- TASK-001～074中出現的Draft PR、不得push／PR、merge另批、完整CI或exact merge commit等文字，多數是已完成
  任務的當次授權與執行證據；保留原文，不追溯套用新規則，也不視為目前全域要求。
- TASK-071／072／074與其report／review中要求TASK-073在合併後relock的敘述，屬當時安全修正歷程；對未來
  操作的規範性已由TASK-073現行文字、DEC-073與`COLLABORATION.md`版本1.5取代。
- 任何舊task若日後重開，不得直接沿用其歷史PR／CI／授權條款；Work須先依新版優先序分類為歷史事實、仍有效
  安全邊界或需修訂的流程限制，再更新active task與`HANDOFF.yaml`。

### TASK-075 change-aware CI（2026-08-08）

- Owner已同意依新版規範建立TASK-075；目前交棒Codex，目標是一般純文件走快速gate、服務變更跑受影響suite、
  database／受控artifact才跑PostgreSQL 15／16 matrix，並提供穩定final aggregate gate。
- 本任務承接7份Owner已審閱但未提交的policy／TASK-073文件；不得拆成另一個純文件PR。
- Workflow自身變更使TASK-075唯一final PR必須跑一次完整hosted baseline；完成後日常docs-only PR才不再啟動DB matrix。
- TASK-073在production inventory前安全暫緩；reviewed source commit與三份SQL checksums維持有效，本任務不授權
  production SQL、migration或任何cloud／GitHub settings mutation。

### TASK-073 Phase C production schema migration（2026-08-08）

- Owner依exact checksums執行fresh inventory、唯一一次`0003 -> 0004`transaction及immediate read-only post-check。
- Inventory 51列／38 required gates通過，zero Phase C collisions；session非superuser，BYPASSRLS風險由Owner明確接受。
- Post-check 55列／44 required gates通過，revision為`0004_phase_c_identity_lifecycle`，精確確認2 tables、19 columns、
  15 constraints及3 indexes；10個compare metrics一致，strict compare結果為`pass`。
- Schema migration已完成且不做downgrade。`PORTAL_DATA_PHASE_C_ENABLED`及identity maintenance維持off；尚未部署
  application、改Secret／IAM／Scheduler／RLS／grants、發通知或執行其他production mutation。
- 結案文件保持本機未提交，應併入下一個實質application rollout task，不另開純closeout PR或觸發昂貴CI。

更新時間：2026-08-07T21:51:52+08:00
維護角色：Work
證據基準：PR #38 squash merge `196c2087a1bfdf816f16aafc267c7008aa376f41`

## 1. 目前摘要

- TASK-056 已完成 production `ntubtob` schema custom-format logical backup：archive 保留於 Owner 指定的
  repository 外加密位置；PR #60 Python 3.10 CI 通過並 merge 為 `d8ec8b1`。Owner 另行批准後，Docker
  verifier 已建立 manifest/checksum 並獨立驗證成功（56,903 bytes、client major 16、schema/listing verified）。
  未重跑 dump、未 restore、未執行 SQL／migration 或變更 production schema/cloud resources；isolated restore
  rehearsal 與 migration 仍須另開任務。
- TASK-057 已建立並交棒 Codex：先以假資料建立 fail-closed、無網路／port／persistent volume 的 ephemeral
  Docker restore rehearsal wrapper；本輪不讀或還原 production archive，正式 rehearsal 仍須另行批准。
- TASK-057 已由 PR #61 合併為 `1c07871`，Python 3.10 CI 與 ownership-guarded cleanup通過。TASK-058 已建立
  一次性正式 archive isolated restore rehearsal執行包，等待 Owner批准 exact artifact與 cleanup範圍；尚未執行。
- TASK-058 已依 Owner 精確批准完成：正式 retained archive 的 path preflight、唯一一次 ephemeral restore、13 類
  sanitized catalog checks、restore 前後 verification與 ownership cleanup全數通過；無 container／volume殘留，
  artifact set未變更。這證明 archive可還原，但不取代 Phase A 前的當下 production read-only baseline。
- TASK-059 已開始：Owner批准立即執行既有 reviewed read-only Supabase catalog/access SQL；等待 repository 外
  six-column CSV供 Work驗證。結果只在目前無 schema/access/deployment變更的 migration window內有效。
- TASK-059 baseline已驗證：33 metrics與三個 fingerprints通過，legacy 10 tables、RLS 10/10、無 Alembic marker
  或新表。SQL Editor role是高權限 migration owner。現有 migration artifact缺 baseline marker建立且13張新表
  未 enable RLS，故不得執行；等待 Owner角色/RLS決策後建立 TASK-060，完成後須重跑 execution-time baseline。
- Owner已接受migration-owner高權限邊界並決定13張新表Phase A enable RLS／zero policies。TASK-060已建立並交棒
  Codex，補齊同transaction baseline marker、RLS、verifier與local rollback/lock rehearsal；不授權production。
- TASK-060已由Work驗收為`accepted`：實際implementation commit `97c8ddc1`與diff已查驗，local fake PostgreSQL
  verifier及96項測試全數通過，涵蓋atomic rollback、lock timeout/retry與既存狀態fail closed。等待Owner批准
  push／Draft PR／Python 3.10 CI／squash merge；合併後仍須重跑TASK-059，production migration另需精確批准。
- TASK-060已由PR #62 squash merge為`0d54a4c`；hosted Python 3.10、Black與所有service test steps通過。
  TASK-061已建立為合併後execution-time baseline：Owner須重跑既有read-only SQL並提供repository外CSV，Work
  離線驗證後才提出production migration execution package；目前仍未授權migration。
- TASK-061新鮮baseline已由strict validator驗證33/33 metrics及14項安全測試通過，與TASK-059無drift。準備
  execution package時發現runbook尚無fixed post-check SQL，故先建立TASK-062補齊deterministic pre/post-check、
  去識別化validator與local rehearsal；完成前不得執行production migration或ad-hoc SQL。
- TASK-062補正後已由Work驗收為`accepted`：pre/post固定legacy fingerprints、generic grant/ownership boundary、
  portal non-owner grants與aggregate invariants；Work獨立重跑PostgreSQL 16完整106項tests及artifact verifier通過，
  PR #63最終Python 3.10／Black CI成功。依Owner長期Git授權可自行merge，再建立TASK-063；migration仍另需批准。
- TASK-062已由PR #63 squash merge為`871abd2`。TASK-063 exact execution package已固定三份SQL checksum、retained
  recovery artifact、30分鐘window、freeze、precheck／migration／postcheck與ambiguous-connection recovery流程，
  等待Owner精確批准；尚未讀backup artifact或執行任何production SQL／migration。
- TASK-063已完成backup及artifact preflight、production pre-check與唯一一次Phase A migration。Post-check 51項中
  僅raw `prosrc` function MD5失敗，其餘exact gates通過且legacy counts一致；Work以CRLF在local精確重現誤判。
  TASK-064已獲批准修正read-only fingerprint並補LF/CRLF tests；production schema保留，不重跑或downgrade。
- TASK-064已由Work驗收為`accepted`：只正規化post-check CRLF、LF/CRLF及實質mutation tests通過，Work獨立
  PostgreSQL 16完整108項與artifact verifier成功。新post-check checksum為`8ee0b812...0526a8a7`；merge後只需
  Owner重跑一次唯讀post-check，production schema不再修改。
- Production Phase A已完成：exact migration只執行一次，TASK-064 CRLF-safe final post-check與原pre-check通過
  strict combined validation。Revision為0003、13張新表RLS enabled／zero policies且零application rows，legacy
  fingerprints、grants與counts不變；未backfill、部署或接線，Phase B/C仍須另案批准。
- Owner已核准Phase B產品預設並建立TASK-065：每位永久校友Member建立`basic/inactive` Person，但只有已有
  可靠legacy Member link的LINE identity才取得`team_player`；不因Member身份自動授予球員資格，不自動提升
  admin/officer，不猜測未連結或ignored identity。本任務只製作去識別化盤點與deterministic artifacts並在local
  PostgreSQL演練，尚未授權任何production查詢、backfill或Phase C接線。
- TASK-065已由Work第三輪驗收為`accepted`：修正required-integer與public renderer兩項fail-open問題後，
  PostgreSQL 16 portal_data 121/121通過。Inventory-bound mutation會在寫入前重驗Phase A、legacy counts、forced
  RLS與audit triggers；Member為basic/inactive且僅可靠LINE-linked Member取得team_player。Commit前可exact
  rollback，commit後因append-only audit只能forward compensation。尚未執行任何production inventory/backfill。
- TASK-066已建立為Phase B正式去識別化唯讀inventory execution gate，固定merge commit、SQL checksum、六欄CSV、
  strict validator、freshness/freeze及stop boundary，等待Owner精確批准。此任務不render或執行backfill；正式DML
  仍須後續TASK-067另行批准。
- TASK-066已完成：production唯讀inventory strict validation通過，確認197 Members、65 LINE users，其中56個
  reliable links對應56位Members，4個pending candidates、5個ignored；Phase A與zero-row gates全數正常。
  Owner另批准本機準備TASK-067；repository外rendered SQL已固定為8,853 bytes／SHA-256 `3f9f8844...e8c831`。
  TASK-067 exact execution package等待Owner另行production DML批准，尚未執行backfill或post-check。
- Production Phase B已完成：Owner依TASK-067執行fresh inventory、唯一一次exact backfill與post-check，strict
  compare通過。Production現有197 People/member links、56 LINE identities、56 team_player、309 append-only audits，
  所有關係與安全zero gates正常；其他portal tables仍為0 rows，Phase A boundary不變。未進入Phase C或部署。
  在runtime reconciliation／dual-read策略建立前，Member／LINE identity mapping維護仍維持凍結。
- TASK-068已建立為Phase C前置安全任務：Web Portal配對／ignore將新增預設關閉的server-side maintenance guard，
  並建立去識別化cross-model drift detector；新unlinked／ignored rows只分類、不自動處置。本輪repository/local-only，
  不做dual-write、activation、production query或deployment，等待固定「Codex－實作」session接手。
- TASK-068已由Work第二輪驗收為`accepted`：guard default-off且在副作用前503；drift inventory補齊forced-RLS與
  exact Phase B audit關係gate。Local PostgreSQL 16為128/128，Web Portal 110 passed／2 platform skips，PR #67
  hosted Python 3.10 formatting及所有required suites成功。尚未部署，production配對freeze仍需人工維持。
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

- `TASK-056` 已建立為一次 production logical backup 的精確批准閘門：預定固定 PostgreSQL 16.4 Docker
  client、schema-scoped custom archive、Owner-owned env-file 與加密 repository-external destination；目前尚未
  授權讀 credential、連 Supabase、執行 dump／restore／migration 或處理 production archive。Local preflight
  發現 host 無 `pg_restore`；固定 image、network-none/read-only Docker inspection backend 已通過 Work code／
  tests、real local fake archive create/verify 與 PR Python 3.10 CI 後 merge。Owner 批准的 session-pooler dump
  已建立 56,903-byte archive，但 verifier 將 repository-known `line_notify_tokens` identifier 誤判為敏感 token，
  sidecars 未建立；archive 保留且不重做 dump，先離線修正 verifier，再另行批准 re-verify。
- `TASK-055` 已通過 Work 驗收：repository-only artifact verifier、fixed manifest/checksum、backup/recovery
  runbook 與 migration gates 完成；isolated PostgreSQL 16.4 fake dump/list/restore、row/sequence/RLS/constraint
  fidelity 及 real-listing parser 均通過。Production backup 尚未建立，Phase A migration 仍 blocked；下一步
  需先以 PR CI 補 Python 3.10 證據，再由 Owner 另行批准精確 production backup execution 工作包。
- `TASK-054` 已完成控制面盤點：`ntubtob` 未暴露於 Data API，runtime 使用 session pooler、migration
  預定 direct connection，maintenance window 與 bounded timeout 可接受；但 backup、PITR 與 retention
  均不存在，故 Phase A migration 維持 blocked。下一步優先建立 logical backup 與 restore-readiness 工作包。
- `TASK-053` 已通過 Work 本機驗收：validator 只正規化三個 value 欄位的 standalone `null`，14 項
  regression tests 與 compile 通過；repository 外的 Owner CSV 已唯讀驗證為固定 33-row contract，未印出、
  複製或提交原始資料。Python 3.10 hosted runner 與格式工具證據待 PR CI 補足；未連 Supabase 或修改任何
  schema／RLS／role／backup 設定。
- `TASK-052` 已通過 Work 驗收：已準備 transaction-level read-only SQL、固定
  catalog/function allowlist verifier、33-metric 去識別結果 contract／validator、虛構 fixture 與
  Owner SQL Editor／Dashboard checklist。Work 額外在 local fake baseline 驗證 query 語法與固定
  33-row 輸出；未連 Supabase、未執行 production SQL 或任何 schema／RLS／backup 變更。後續真正
  SQL Editor 執行仍需 Owner 另行批准。
- `TASK-051` 已通過 Work 驗收：固定 `0001 -> 0002 -> 0003` 的
  deterministic upgrade-only SQL／SHA-256、fail-closed verifier、transaction failure／bounded
  lock rehearsal、RLS 決策包、去識別 evidence template 與 production runbook 均已建立。
  Python 3.10 的 43 項 portal-data tests、完整 migration chain、compile、Black／isort 與 `alembic check` 通過；
  task-owned container 已停止且 named volume 保留。未連 Supabase、未執行 production schema
  操作；backup/PITR、runtime role/table owner、API exposure 與新 tables RLS 仍是 production 前
  Owner 決策／查證閘門。
- `TASK-050` 補正後已通過 Work 離線驗收：local exact-schema fixture、bigint migration、
  deterministic attendance projection 與 Alembic ownership boundary 均已建立。Python 3.10 的
  35 項測試、完整 downgrade／fixture rebuild／upgrade chain、compile 與 `alembic check` 通過，
  且沒有新 upgrade operations。未連 production、未做 DDL／stamp／backfill；production RLS、
  backup／PITR、lock time 與 rollout compatibility 仍留待後續規劃與 Owner 明確授權。
- `TASK-049` 已完成 Supabase production schema 與 aggregate data-quality 唯讀盤點：
  兩次 transaction 都為 read-only，未讀 application row values。確認 production 有
  10 張 legacy tables、197 Members、65 LINE users、128 Games 與 1,648 attendance rows；
  無 orphan 或 identity collision。106 組 attendance duplicates 含 144 次真正狀態變更
  與 9 次連續相同回覆，沒有 exact duplicate、timestamp tie 或 identity mismatch；legacy
  history 不可刪除或直接加 unique constraint。下一步為離線 exact-schema migration
  rehearsal。尚未授權 production DDL、stamp、backfill、RLS、Secret 或 deployment。
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

### TASK-046 Attendance延遲分段量測（2026-08-06）

- 已為成功`/attendance`response建立固定、無個資的Member lookup、games query、attendance analysis、render與total milliseconds診斷。
- clock／logger故障不影響頁面；所有值clamp至`0..300000ms`，不改request timeout，亦不增加model/analyzer呼叫。
- Work獨立驗證109項Web Portal測試通過（2項既有Windows skip）、compile與diff check通過；結論為`accepted`。
- 尚待Owner批准PR／部署後取得production timing；application stages仍須搭配Cloud Run request latency判讀cold start。

### TASK-045 移除過時attendance cache request（2026-08-06）

- LINE webhook出席回覆已不再同步呼叫不存在且無timeout的Web Portal cache endpoint；無caller的`shared_module.web_cache`已移除。
- DB add、回覆訊息、相同回覆、過期／取消、首次提示與12小時內管理通知行為均由fail-on-network離線測試保護。
- Work獨立驗證18項webhook與101項Web Portal測試通過（2項既有Windows skip）、compile、shared sdist build與diff check通過；結論為`accepted`。
- 尚待Owner批准PR工作包；後續若部署，只涉及LINE webhook Gen2 function與重建shared artifact，不需Web Portal部署。

### TASK-044 LINE登入目的地安全診斷（2026-08-06）

- 完整離線登入鏈證實現有程式會從`/attendance`成功登入後返回`/attendance`；production落到`/`的現象尚未在repository重現，因此未加入猜測性redirect修正。
- 已新增固定allowlisted目的地分類診斷，不記錄URL/query、OAuth、cookie、LINE／Member或Secret資料；診斷故障亦不影響成功登入。
- Work獨立驗證99項Web Portal測試通過（2項既有Windows make/sh skip）、compile與diff check通過；結論為`accepted`。
- 尚待Owner批准PR與部署後重做LINE App流程，再依安全category定位production差異。

### TASK-041～043 Web Portal production rollout（2026-08-06）

- PR #49經Python 3.10 CI成功後squash merge為`9deb7e11311d5ccdb4131cb3b13a318a6bceca60`。
- Production部署成功：Cloud Build `a1902e48-ed13-480d-9097-e1b180fbc4c5`，新revision `web-portal-00037-lhx` Ready並承接100% traffic。
- 首頁唯讀HTTP check為200，`/demo/`為404；未需要rollback。
- 未操作Secret／IAM／Scheduler／schema／data／LINE或其他服務；真實瀏覽器的帳號、導覽與視覺體驗仍由Owner人工確認。
- 完整證據見`docs/operations/deployments/WEB_PORTAL_9DEB7E1.md`。

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

### TASK-069 Web Portal identity maintenance guard production deployment（2026-08-07）

- Owner批准將`44acdcd1576be57fe2d9c08861872fa75146a2ef`部署至production `web-portal`。
- 部署前`web-portal-00039-87s` Ready且承接100% traffic，作為exact rollback target。
- Cloud Build `e8534be4-cb7a-4efc-814d-ba4fa735ccf4`成功；新revision `web-portal-00040-wm9`
  Ready並承接100% traffic，image digest為`sha256:1c4ec082515fd0369ead487ccf02137fa76b42fb666bf4fae47a90a78c6cf01c`。
- 首頁200、production demo 404、public IAM與runtime Secret classifications維持；新revision 30分鐘範圍內
  ERROR log為0，未觸發rollback。
- Maintenance flag維持不存在／default-off，因此legacy match／ignore POST在production fail closed；未做具副作用的
  管理POST、DB、LINE／Discord、Secret、IAM、Scheduler、schema或其他服務操作。
- 完整證據見`docs/operations/deployments/WEB_PORTAL_44ACDCD.md`及`docs/coordination/reviews/TASK-069-WORK.md`。

### TASK-070 Phase C identity lifecycle與Person-based attendance（2026-08-08）

- Owner已批准repository／local-only實作及一般Git／PR工作包，交由Codex執行。
- 範圍擴大為完整Phase C application bridge：transactional identity lifecycle、Person status／names／qualifications、
  pending核可對話、LINE principal/session、mobile-first admin UI及Person-based legacy attendance。
- 所有active Person可查看賽事；active team_player與有期限guest_player可由Portal／LINE回覆。Guest未回覆不計入
  尚未回覆；一般頁面不列舉尚未回覆姓名，姓名可切換display／formal。
- Repository將新增0003後的expand migration及local rehearsal；production migration、Supabase操作、部署、真實通知與
  maintenance flag啟用仍須另案批准。
- 過渡期只有現有Web Portal admin allowlist可管理；People role cutover、Person merge、Event eligibility及正式
  Google／Apple OAuth不在本任務。

### TASK-071 Phase C production migration readiness（2026-08-08）

- Repository-only readiness package 已由 Work 接受：包含 checksummed inventory／migration／post-check SQL、strict
  validator、compare、runbook 與 recovery boundaries。
- Post-check 精確 fingerprint 19 個 Phase C-owned columns、15 個 constraints 與3個 indexes，並驗證
  RLS／forced-RLS／zero-policy boundary；負向 catalog mutation 測試會 fail closed。
- Work 獨立驗證 localhost-only PostgreSQL 16 完整155項測試及三個 verifier通過。
- 尚未取得 fresh production inventory、執行 production migration、部署或開啟 runtime flags。

### TASK-072 Phase C repository integration（2026-08-08）

- 目標是以 required CI 與 squash merge 將 TASK-071 readiness package 整合至 `main`，鎖定後續 migration task 的
  exact merged commit。
- PR #69 的Python 3.10 CI成功，已squash merge為`36016ee80911f98db1f638b43550e77fc75e87b1`；本機
  `main`已同步，原始多commit歷史保留於local archive branch。
- 本任務不授權 production database、migration、deployment、runtime flags、Secret／IAM／Scheduler或通知操作。

### TASK-073 Phase C production migration execution（2026-08-08）

- 已鎖定merged commit及inventory／migration／post-check三份SQL checksum，等待Owner先批准production read-only
  inventory collection。
- Work驗證30分鐘內fresh inventory後，Owner仍須另行批准exact migration window；read-only批准不包含DDL／DML。
- Migration成功後runtime flags仍保持關閉；application deployment與staged activation另立任務。

### TASK-074 PostgreSQL 15 Phase C readiness修正（2026-08-08）

- 第一份TASK-073 fresh inventory唯一required failure為production PostgreSQL 15不符合錯誤的version-16 gate；依
  fail-closed規則停止，未執行migration／DDL／DML，資料異動freeze已解除。
- 修正任務要求PostgreSQL 15與16皆通過相同exact catalog fingerprints、migration／post-check／compare及failure
  rehearsals；PostgreSQL 14以下與未知版本必須fail closed。
- TASK-074合併後將重新鎖定commit與三份SQL checksums，再回到TASK-073取得新的30分鐘fresh inventory。
- Work獨立驗證PostgreSQL 15.8與16.4各157項測試通過；PR #71 hosted matrix兩個Python 3.10 jobs亦成功，
  exact catalog fingerprints未弱化，驗收結論為accepted。
- PR #71已squash merge為`5cdedd60d999a095a66230101818fdaa31acd46d`；TASK-073已重新鎖定新inventory／
  post-check checksums，等待Owner重新批准並提供fresh read-only inventory。

### TASK-076 Phase C跨服務啟用準備（2026-08-08）

- Production schema已完成0004 migration，但runtime flags仍維持off；本任務只完成repository-only rollout準備。
- 已建立三服務共同exact-`true`旗標狀態機；maintenance不能在Phase C off時生效，任一單服務／雙服務mixed vector
  會被preflight拒絕。
- Portal／Webhook／notify共用PostgreSQL 0004 attendance與identity contract；compatibility adapters只保護過渡資料，
  不把mixed mode宣稱為normal-traffic相容。
- Shared artifact source fingerprint、三份deployment artifacts、requirements與build-context exclusions皆有離線檢查；
  `game_broadcast_service`經查不是Phase C direct caller。
- Work風險式驗收沒有blocking finding；唯一ready PR仍須取得hosted Python 3.10／PostgreSQL final gate後才能merge。
- 後續TASK-077若要部署或啟用，必須另取Owner對exact commit／revisions、runtime flags、可驗證attendance／notification
  freeze、observation、production smoke及rollback traffic mutation的明確批准；無freeze則activation blocked。
- PR #77 final hosted CI全部通過，已squash merge為`43eb67c`；未部署且所有Phase C runtime flags仍關閉。

### TASK-077 Phase C跨服務freeze gate（2026-08-08）

- 三服務共用exact freeze state、零副作用freeze boundaries與離線transition controller已完成。
- Work首次驗收發現shared runtime的CI consumer分類漏測；修正後runtime變更會跑Web Portal、Webhook、notify與
  deployment tools，但不因本身觸發PostgreSQL matrix。
- PR #78 hosted final gate全數通過，已squash merge為
  `1838ec6fc77a74e23700f9cd29b8ea910c0a29fb`。
- 尚未部署；production Phase C、freeze與identity maintenance flags仍預期維持off，實際值須由TASK-078唯讀盤點確認。

### TASK-078 Phase C feature-off deployment準備（2026-08-08）

- 先建立三服務exact artifact、production current／rollback revision、非機密flag vector與停止條件的部署工作包。
- 本階段僅允許repository／local工作及production唯讀`describe`／`list`；不build、deploy、切traffic、改env、invoke、
  操作Scheduler／Secret／IAM／DB或發送通知。
- Work查驗工作包後，須由Owner另行批准exact commit、targets與rollback範圍，才可執行production部署。
