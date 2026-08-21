# 專案狀態

更新時間：2026-08-21T18:15:00+08:00

維護角色：Work

Repository 基準：`main` / `d3ea563b322c5f711d591929509886b556dfff59`

## 目前摘要

- TASK-140 Flutter schedule usability 已由 PR #162 merge 至 `main`（`d660bf46356c14cf21c45a08c2797690e5b38209`）：
  authenticated refresh具備合併與logout command雙層競態防護，賽事採穩定排序與可讀本地時間；hosted Flutter
  format/analyze/full tests/fake APK/final gate全綠。未執行TASK-133 Resume或staging runtime。
- TASK-141 Flutter帳號與資料狀態頁已由PR #163 merge至`main`（`d3ea563b322c5f711d591929509886b556dfff59`）：
  只顯示既有display name、本地last sync與fresh/offline/unknown provenance；offline／unknown為唯讀非權威，無新增API、
  權限或設定副作用。Hosted Flutter format/analyze/141 tests/fake APK/final gate全綠。

- TASK-133 repository delivery／hosted CI 證據已接受；E2E staging dogfood 仍為 inconclusive，因 standalone status
  可 PASS、完整 Resume observation 偶發 `STATUS_UNAVAILABLE`。既有 `await_observation` checkpoint 保留且不再重試。
  原子 launcher、fictional fixture/operator、no-disclosure broker、固定 redacted JSON 與 checkpoint primitive 繼續作為
  可重用基礎；完整 acceptance orchestration 與 UIAutomator timing retry 僅供 experimental/manual-on-demand，不作 release gate。
- TASK-113 isolated mobile staging 已建立並部署；TASK-118 已修復 fictional attendance fixture/recovery，均未觸及
  production。TASK-115 Android emulator 已完成 native LINE callback、Basic API、五態回覆恢復、offline cache 與
  logout purge 驗收，並由 PR #129 merge 至 `main`（`d4569577817a18e74758dad61bfaff2b82991f85`）。TASK-119 將補
  fictional staging 的 Officer 唯讀 report/capability/downgrade acceptance；實體 Android 與 iOS gate 尚未完成。

- TASK-104／105／107 Flutter client foundation 已由 PR #118 merge 至 `main`（merge commit `da85abddc7e339011df13b021038523e84900631`）；fictional source、Android/iOS runners、Flutter analyze、13 tests與Android debug build已完成，尚無裝置smoke、iOS build/signing或發布。
- TASK-106 schema-neutral attendance reply application service 已由 PR #117 merge 至 `main`（merge commit `b26c1702605e463b96680b6c481b4da95880d198`），Web與LINE共用changed/12小時通知決策。
- TASK-108 mobile contract與TASK-109 Basic mobile API foundation已由 PR #119 merge 至 `main`（merge commit
  `cd28d60d328844f94d9544aa50965cf77cb2399e`）；revision 0005尚未在 production 執行，mobile API亦尚未部署。
- TASK-110 Flutter Basic native auth/API integration已由 PR #120 merge至 `main`（merge commit
  `4792f529a374baa3f87386a0883a6a82c1ecb048`）；真實LINE/staging、Officer/Admin、通知、簽署與發布尚未進行。
- TASK-111 release identity與hosted Flutter CI已由 PR #121 merge至 `main`（merge commit
  `2c33b6e48f89f43a34f44784e9c224971b5cca38`）；hosted format/analyze/71 tests/fake Android build及final gate全綠。
- TASK-112 mobile staging readiness已由PR #122 merge至`main`（merge commit
  `7ef79b1380ac054b867bcac0fd4b2c317b81d778`）；尚未建立或變更GCP、database、LINE channel、Secret、IAM或部署。
- TASK-114 Mobile Officer唯讀出席報告與Flutter parity已由PR #123 merge至`main`（merge commit
  `baee3f93357c1268cd6d8803e053983939fa3a5d`），hosted Flutter 97 tests/debug build與final gate全綠。
- TASK-113 已啟動：先在E槽建立本機Android Emulator並做fake smoke，再提出dedicated staging外部資源與成本的
  精確Owner批准manifest；目前未建立或變更任何雲端、DB、LINE、Secret或IAM資源。
- Flutter planning 已確認 Android／iOS staging APK／TestFlight 測試路線；production、schema、Secret、IAM、正式通知與商店發布仍未授權。

- Phase C 已完成 production schema、跨服務 runtime 啟用、管理入口 bootstrap 與既有可靠 LINE 隊員啟用。
- Production 目前有 197 位永久 Member 對應 Person；56 組可靠 LINE identity／active team-player 關係。
- 2 位 allowlist 管理者與其餘 54 位既有可靠連結隊員的 Person 均已由 `inactive` 啟用為 `active`。
- TASK-087 production post-check 已驗證：2 位管理控制組不變、54 位 cohort 全部啟用、54 筆新 audit、drift 0，
  Member／identity／legacy LINE／qualification／attendance cardinality 不變。
- TASK-088 delivery group `phase-d-identity-admin-transition` 已由 Work 驗收接受並 squash-merge 至 `main`（merge commit
  `4903ddd0f7ee8abb2c621221dce395ccf81bb125`）。
- TASK-089 `phase-d-identity-admin-operations` 已由 Work 驗收接受並 squash-merge 至 `main`（merge commit
  `5afa79c0c4ff3a79eeae2c7bd74d87eb55afbe5f`）。
- TASK-090 `phase-d-capability-and-smoke` 已完成 planning，決策已併入 TASK-091。
- TASK-091 `phase-d-capability-and-smoke` 已由 Work 驗收接受並 squash-merge 至 `main`（merge commit
  `72234fbe3c4b024716798c0cd603e9ea0912cffb`）。
- TASK-092 `phase-d-qualification-and-game-operations` 已由 Work 驗收接受；確認既有 qualification／Game contract 已
  覆蓋規則，未重複新增程式碼。Event/Activity 延後。
- TASK-096 `phase-d-web-ui-refresh` 已由 Work 驗收、通過 hosted Python 3.10 CI，並由 PR #106 squash-merge 至
  `main`（merge commit `1f06a18a95f3e86c24825f1eb7ab6282034972da`）；未部署。
- TASK-097 `phase-d-local-cloud-data-preview` 已由 PR #107 squash-merge 至 `main`（merge commit
  `6b43ab1c39639117ec0c0e555eca3668199bb321`）；實際 Supabase 匯出仍需另行精確批准。
- TASK-098 已由 PR #108 squash-merge 至 `main`（merge commit `44925dad735e8ee3d28ac0f9dae0cb2535762496`）；
  Officer／Admin Game command center、attendance insights 與 session-only 粗／細守位試排尚未部署。
- TASK-099 `phase-d-portal-management-closure` 已完成 planning，下一步修正 localhost 驗收發現的 role assignment、
  navigation、Windows Attendance、preview Admin parity，並正式化 repeatable fictional local UI demo。

## 已確認的 production 狀態

### 資料庫與身分資料

- PostgreSQL schema：`ntubtob`。
- Alembic revision：`0004_phase_c_identity_lifecycle`。
- Phase A 建立 portal-data schema boundary；新表採 RLS enabled／zero-policy 的 fail-closed 基準。
- Phase B 完成 deterministic backfill：197 People／Member links、56 LINE identities、56 active `team_player`、309 筆
  append-only audits；當時 strict post-check 無 orphan、duplicate 或 qualification drift。
- Phase C identity lifecycle、Person-based attendance、pending review conversation 與 audit actions 已建立。
- 2026-08-09 完成管理與隊員啟用：先啟用 exact-two allowlisted administrators，再啟用其餘 54 位 existing
  reliably linked team players；兩次 mutation 均以精確 cohort、單一 transaction、post-check 與 retry verification 完成。
- 管理權限目前仍以 Web Portal runtime allowlist 為準；Person 的 portal access level 尚未取代 allowlist。

### Runtime 與服務

- Web Portal、LINE webhook、notify cron 的 Phase C flag 已啟用，freeze 已解除；identity maintenance flag 仍維持
  false，除非後續任務以新的精確邊界啟用。
- Phase C activation 時的 production revisions：
  - Web Portal：`web-portal-00046-g8v`，100% traffic。
  - LINE webhook：`line-webhook-handler-00013-yab`，100% traffic。
  - Notify cron：`notify-cronjob-service-00017-qms`，100% traffic，維持 private。
- Web Portal 與 LINE webhook 維持必要的 public ingress；LINE webhook 必須驗證 signature。
- Game broadcast 不是 Phase C direct caller；update schedule 未納入 Phase C runtime activation。
- LINE access token／channel secret 已由 Secret Manager version 2 綁定；plaintext keys 已自 active `.env.yaml` 移除。
- 已棄用 LINE Notify API 與 legacy `line_notify_tokens`；LINE Official Account／Messaging API、LINE Login／webhook
  與 Discord 仍是分開存在的能力，必須依實際 caller 查證。

### Git 與 CI

- TASK-087 PR #98 已通過 hosted PostgreSQL 15／16、各服務 suites、deployment tooling 與 final gate，並 squash
  merge 為 `ab1efa1579c688e71720b471ea1b3b5226447adc`。
- 一般 Git 操作具有 Owner standing authorization；production deployment、production DB mutation、Secret／IAM／
  Scheduler／cloud resource 變更與真實通知仍需個別明確批准。

## 尚未驗證與已知限制

- 啟用 56 位 Person 後尚未由 Owner 做一次一般瀏覽器與 LINE in-app browser 的人工登入／頁面 smoke；production
  post-check 已證明資料狀態，但不等於使用者端完整操作驗收。
- 自然 Scheduler 執行與低流量環境的長期 observation 不足；不得以缺少 error log 推定所有通知情境都已覆蓋。
- Identity maintenance 仍為 false；新 pending identity 的 match／ignore／remap 等正式操作需另行規劃啟用與驗證。
- People role 尚未取代 runtime admin allowlist；officer／admin 的正式持久化權限切換仍屬 Phase D 之後工作。
- Event／Activity、多場比賽、旅遊與 guest-player eligibility 尚停留在規劃／Demo，不代表正式 schema 或 production 功能。
- Google／Apple OAuth 仍只有 prototype UI，尚未實作。
- Attendance 首次載入可能受 Cloud Run／資料庫 cold path 影響；現階段接受延遲，後續應先量測再改架構。

## 下一階段候選方向

### P1：Mobile isolated staging readiness

- TASK-112 先完成dedicated staging project/database/LINE channel operator與費用、IAM、rollback批准manifest；不做外部mutation。
- TASK-112 merge後由Owner精確批准TASK-113 activation，才建立staging、部署mobile API並做Android真機LINE smoke；iOS留macOS gate。
- 既有 pending identity、runtime allowlist／capability cutover 與 bounded Game command center 仍依既有 task／DEC 處理，不因 Flutter planning 自動擴張。

### P2：Event 與多元活動

- 將 Event／Activity、複合行程、非聯盟比賽、聚餐、旅遊與 guest player 從 Demo 收斂為正式 domain design。
- 在 schema 前先定案活動參與資格、幹部建立權限、邀請快照與資格異動語意。

### P3：工程與維運健全性

- 將文字 artifact checksum 統一為 canonical LF helper，補 LF／CRLF CI regression。
- 完成 branch protection／required final gate 後，評估移除 main push 的重複昂貴 suite。
- 依實際 observation 評估 attendance cold-start／pooling／query，再決定是否需要 cache。

## 協作與文件入口

- 當前狀態與下一位角色：`docs/coordination/HANDOFF.yaml`。
- 協作、TASK／Push／PR 與 CI 規則：`docs/coordination/COLLABORATION.md`。
- 長期決策：`docs/coordination/DECISIONS.md`。
- Phase C 摘要與歷史索引：`docs/coordination/archive/phase-c/PHASE_C_CLOSEOUT.md`。
- 封存文件預設不讀；只有調查歷史決策、事故或 rollback 證據時才查閱。

## 安全邊界

- 不因 Phase C 完成而自動授權任何新 deployment、production DB 操作、Secret／IAM／Scheduler 修改或通知。
- 不讀取或提交 `envs/**/.env.yaml`、private backup env 或 Secret payload。
- Production mutation 固定採 discovery → Owner 精確批准 → 單次執行 → post-check；不確定結果改走獨立唯讀
  recovery diagnostic，不重跑 mutation。
