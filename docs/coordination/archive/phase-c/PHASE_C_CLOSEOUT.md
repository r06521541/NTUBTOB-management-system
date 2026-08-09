# Phase C Closeout

結案日期：2026-08-09

狀態：production 功能與資料啟用完成

最終 repository 基準：`ab1efa1579c688e71720b471ea1b3b5226447adc`（PR #98）

## 管理摘要

Phase C 已將 legacy Member／LINE 關係延伸為 Person、auth identity、qualification、audit 與 Person-based attendance
模型，並完成 Web Portal、LINE webhook、notify cron 的 staged rollout。Production 最終有 197 位永久 Member 對應
Person、56 組可靠 LINE identity／active team-player；2 位 allowlist 管理者與其餘 54 位既有可靠連結隊員均為
active。最後兩次受控 activation 的 post-check 均通過，沒有 Member、identity、LINE link、qualification、attendance
或 schema drift。

## 完成範圍

### Schema 與資料

- Phase A：建立 portal-data schema／migration boundary，RLS enabled、zero-policy fail closed。
- Phase B：deterministic backfill 197 People／Member links、56 LINE identities、56 active `team_player`、309 audits。
- Phase C：migration 至 `0004_phase_c_identity_lifecycle`，加入 identity lifecycle、Person names／status、qualification、
  pending conversation、audit actions 與 Person-based attendance contracts。
- Zero-admin bootstrap：以 runtime allowlist 作管理權限真實來源，啟用 exact-two 管理者 Person，不把 Person role 誤當
  production admin authority。
- Existing-player activation：唯讀 discovery 證明 54 位 eligible cohort；Owner 精確批准後在單一 transaction 啟用，
  新增 54 筆 null-actor `status_changed` audits，retry verification 通過。

### Runtime 與部署

- Web Portal、LINE webhook、notify cron 使用共同 fail-closed Phase C state machine。
- 三服務完成 feature-off deployment、freeze、旗標啟用、解凍與 post-check；mixed vector 不視為正常流量模式。
- Phase C activation revisions：Web Portal `web-portal-00046-g8v`、LINE webhook
  `line-webhook-handler-00013-yab`、notify cron `notify-cronjob-service-00017-qms`。
- Regional Cloud Build submit／resume、candidate／digest／traffic／rollback 驗證邊界已修正並具離線 regression。
- LINE access token／channel secret 使用 Secret Manager version 2；active `.env.yaml` 不再保存這兩個 plaintext key。

### 使用者可見能力

- 已登入且 active 的 Person 可使用 Phase C Web Portal 能力，不應再因舊資料預設 inactive 而全部落入等待核可。
- Member 配對、LINE principal、team-player／guest-player eligibility、attendance reply 與姓名顯示具有共同 domain
  contract。
- Pending identity、管理者核可對話與管理 UI 已具程式基礎；identity maintenance 的 production 操作旗標仍保持
  false，需 Phase D 另行啟用。

## 最終 production 驗證

### Exact-two 管理者

- Preflight：2 位 allowlisted Member、active administrators 0、drift 0。
- Execute：activation +2、audit +2。
- Post-check：2 位 active control、retry verified、drift 0。

### 既有可靠連結隊員

- Read-only discovery：eligible cohort 54、active controls 2、drift 0、mutation 0。
- Execute：activation +54、audit +54。
- Post-check：verified、retry verified、drift 0；Member／identity／legacy LINE／qualification／attendance aggregates
  不變。

### Hosted CI

- PR #98：PostgreSQL 15.8、PostgreSQL 16.4、Web Portal、LINE webhook、notify cron、game broadcast、update
  schedule、deployment tooling、quick gate 與 final gate 全部通過。

## 未完成但不阻擋 Phase C 結案

- Owner 尚未在 activation 後做人工作業 smoke；建議下一次方便時驗證一般瀏覽器與 LINE in-app browser。
- Identity maintenance flag 仍為 false；新 pending identity 的正式核可／拒絕／ignore／remap 是 Phase D 工作。
- People role 尚未取代 runtime admin allowlist；持久化 officer／admin 與 last-admin cutover 是 Phase D 工作。
- 低流量環境缺少有代表性的長時間 observation；自然 Scheduler 與通知結果應以後續實際事件觀察。
- Event／Activity、複合行程、guest-player 活動參與規則與 Google／Apple OAuth 不屬 Phase C。

## Rollback 與資料語意

- Phase C schema 與 production data 已投入使用，不以 destructive downgrade 作一般 rollback。
- Append-only audits 不刪除；若日後發現語意錯誤，以另案 forward compensation 處理。
- Runtime 異常優先使用既有 revision／traffic rollback 與 feature flags；不得以 ad-hoc SQL 修復 Person／identity／
  qualification 關係。
- 任何不確定 production mutation 結果均先走獨立唯讀 recovery diagnostic，不重跑 mutation。

## 歷史範圍

本 closeout 濃縮 TASK-048～087。原始任務、Codex reports 與 Work reviews 保留於同目錄的 `tasks/`、`reports/`、
`reviews/`，預設不納入新 session 的啟動閱讀。
