# 專案狀態

更新時間：2026-08-09T23:17:27+08:00

維護角色：Work

Repository 基準：`main` / `4903ddd0f7ee8abb2c621221dce395ccf81bb125`

## 目前摘要

- Phase C 已完成 production schema、跨服務 runtime 啟用、管理入口 bootstrap 與既有可靠 LINE 隊員啟用。
- Production 目前有 197 位永久 Member 對應 Person；56 組可靠 LINE identity／active team-player 關係。
- 2 位 allowlist 管理者與其餘 54 位既有可靠連結隊員的 Person 均已由 `inactive` 啟用為 `active`。
- TASK-087 production post-check 已驗證：2 位管理控制組不變、54 位 cohort 全部啟用、54 筆新 audit、drift 0，
  Member／identity／legacy LINE／qualification／attendance cardinality 不變。
- TASK-088 delivery group `phase-d-identity-admin-transition` 已由 Work 驗收接受並 squash-merge 至 `main`（merge commit
  `4903ddd0f7ee8abb2c621221dce395ccf81bb125`）。
- TASK-089 `phase-d-identity-admin-operations` 已由 Work 驗收接受並 squash-merge 至 `main`（merge commit
  `5afa79c0c4ff3a79eeae2c7bd74d87eb55afbe5f`）。
- TASK-090 `phase-d-capability-and-smoke` 現為 planning，先收斂 Basic／Officer／Admin capability 與非 production
  browser／LINE in-app smoke 契約，不直接修改程式或 production。

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

### P1：Phase D 身分與管理能力

- 將新 pending identity 的核可、拒絕、留言與提醒流程正式投入使用。
- 規劃 runtime allowlist 至持久化角色／capability 的安全 cutover；保留 last-admin、self-lockout、audit atomicity。
- 為管理者建立可用且可稽核的 Person／identity／qualification 管理介面。
- 完成人工登入 smoke，確認 active Member 不再落入「尚待核可」。

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
