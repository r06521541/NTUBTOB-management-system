# 專案狀態

更新時間：2026-08-31

維護角色：Main Work

Repository 基準：`main` / `d59663781c5602e1699f812d5a953cec12e0eeb4`

## Active role lanes

Flutter 目前為 Owner 核准的產品孵化期：純 UI／導覽／local state／fixture／prototype model 可在具名 incubator
delivery group 的共同 branch 以 focused local evidence 與描述性 commits 持續累積；完整流程、3–6 commits 或一週僅為
checkpoint 提示，不自動建立 PR。接近部署／正式發布候選時才建立唯一 final PR／Hosted CI。Auth、安全、後端契約、shared boundary、正式資料、Secret、schema、
真實通知與部署不適用此例外。TASK-149 已在採用本模式前由 PR #177 合併完成，不追溯改制。

| lane | current actor_id | claim_id | lease_version | state |
| --- | --- | --- | --- | --- |
| `main-work` | `01a03587-d263-7e92-9965-54816f38b8a3` | `main-work-20260825` | 17 | active |
| `domain-work:flutter` | `01a01212-72dc-7132-b2d7-dfaa2f97f184` | `flutter-domain-20260821` | 2 | active |

Lane 是長期責任邊界，不永久綁定厚重 session；輪替須先 revoke current actor，以 full HEAD、dirty state、完成／剩餘事項
交棒，再更新本表。沒有 active task claim 的其他 session 一律為 `advisor/read-only`；通知訊息不得取代本表或 task claim。
Owner 已於 2026-08-25 撤回 `main-work-20260822`，並以本表的 lease 17 取代；舊 actor 回報 worktree clean、沒有
未完成 repository work，可安全封存。Flutter Domain lane 未被撤回，持續有效。

## 目前摘要

- TASK-169 的唯一 PR #219 已完成獨立 Release／Security review並通過 hosted run `33331387388` 的全部selected gates，現為無衝突待合併：Android Basic-only Closed Testing repository readiness包含API 36、外部簽章注入、fictional signed AAB與strict inspector；iOS建立TestFlight／Sign in with Apple fail-closed contract與store compliance matrix。這不是store candidate或外部rollout；未操作store、signing Secret、provider、cloud、production或deployment。
- TASK-168 已由 PR #217 合併為 `cabdbcd039c9d526adb21fd8b11e145cd48f2574`：Event／一般 Activity 採既有三態出席；linked Game 在同一 Event 畫面沿用既有五態 Game attendance，套用全部明確排除 linked Game，且兩者不得互相覆寫或重複儲存。獨立 Data／Authorization review及全部selected hosted gates通過；未執行 schema、通知或部署。
- TASK-167 已由PR #216合併為`10d7cee44b6bd6ff2edb456518a129ebb3692443`：staging APK同時包含arm／arm64／x64 Flutter runtime，build與install acceptance會驗證唯一、非空、可完整讀取且CRC32一致；Android 15 arm64實機替換安裝與冷啟動通過，之後已移除exact package。Hosted全部selected gates通過，借用裝置未登入個人provider帳號。
- TASK-166 已由PR #215合併為`0d6efacac2f20fe1ff66f1aa9ae84fd888ab0961`並部署至production `web-portal-00054-rtp`：桌面登入先切至固定callback origin，以短效簽章且防同瀏覽器重播的initiation落地session，再前往LINE；state／nonce／TTL／safe-return及LINE in-app行為維持不變。Production pre-provider smoke通過且未接觸LINE provider；未操作Secret或正式資料。
- TASK-165 已由PR #213合併為`9c7b82b3857a20c6e53f99d108264a04726aac2f`並部署至production `web-portal-00053-wzw`：Event管理routes、hub、全域導覽及PostgreSQL repository統一依runtime allowlist與`MANAGE_EVENTS`授權，persisted role fallback只限local fictional preview。Hosted PostgreSQL 15／16、Web及final gate全綠；Ready／100% traffic、runtime identity、四個Secret references、admin allowlist、flags、public IAM與HTTP post-check均通過，未需rollback。未建立Event、寫入database、修改Secret／IAM／provider或發通知。
- TASK-164 recovery 已由PR #212合併為`6b0aa7e556d25cb906bf12f4ea0c7eed57705f13`；受控operator將production schema由`0004_phase_c_identity_lifecycle`依序升至`0009_event_management_writes`，application DML count為0，並部署`web-portal-00052-xcg`。該revision現為TASK-165的healthy rollback基準；未建立Event、發通知或修改Secret／IAM／provider。
- TASK-163 已由 PR #209 合併為 `c1dd1e3e75e373da6991748b8e34ab63d86b1c25`：active Officer／Admin 可管理
  Event草稿、Activity行程、資格池與人工override，發布immutable invitee snapshot，並稽核published edit／cancel。
  Hosted run `33077406624` 的PostgreSQL 15／16及全部selected gates通過；尚未roll out schema、部署、發通知或操作正式資料。
- TASK-162 已由 PR #207 合併並部署至production `web-portal-00051-p4z`：同日賽事統一使用完整Dashboard game card，
  所有Dashboard出席POST先經站內可存取確認對話框，JS不可用時fail closed。Ready／100% traffic／public invoker／
  runtime identity／四個既有Secret references與HTTP post-check均通過，未需rollback；未修改backend、provider、Secret、IAM或正式資料。
- TASK-161 已由 PR #205 合併並完成 production deployment：Web Portal 以 exact merged artifact 更新至
  `web-portal-00050-zkl`，identity maintenance維持true、identity-link明確disabled，六個identity-link runtime keys缺席；
  Ready／100% traffic／public invoker／runtime identity／四個既有Secret references及HTTP post-check均通過，未需rollback。
  未修改provider、Secret、IAM或正式資料。
- TASK-160 已由 PR #203 合併：桌面 LINE 登入建立 fresh browser-bound transaction且不改 LINE in-app、Dashboard
  reply CSRF可用、People預設只顯示active、pending identity chooser只列eligible Member，並將同日賽事歸入同一
  比賽日。Writer／獨立 Auth／Identity review／Main及hosted gates均通過，且已由TASK-161部署；provider／Secret／
  正式資料未修改。

- Flutter client foundation、native LINE/mobile API、Basic/Officer唯讀功能、schedule usability及帳號／資料狀態頁皆已整合；
  Google 登入與跨 provider identity recovery repository delivery 亦已由 PR #180 合併。Production mobile deployment、
  iOS signing/TestFlight與商店發布仍未授權或完成。
- Isolated fictional mobile staging、fixture/operator、no-disclosure broker、固定redacted JSON、atomic launcher及checkpoint
  primitive可重用，且未觸及production。完整acceptance orchestration／UIAutomator timing retry僅供
  experimental/manual-on-demand，不作merge或release gate；其E2E dogfood結論仍為inconclusive。
- TASK-088～122及TASK-123～138、140、141已移入phase closeout archive；TASK-142～145的完成文件尚待下一次
  phase closeout批次封存。歷史task只在named delivery、incident、migration或rollback調查時讀取。
- Phase C production schema、跨服務runtime、管理bootstrap與56組可靠LINE identity／active team-player關係已完成；
  管理權限仍以Web Portal runtime allowlist為準。
- TASK-142 已由 PR #168 合併：線上賽事清單支援下拉重新整理，空清單亦可操作；沿用既有 single-flight reload，
  離線仍無 pull action。Focused local verification、Main review與一次 change-selected hosted Flutter gate均通過，
  未使用 emulator／staging／acceptance harness。
- TASK-143 已完成 L1 Flutter game-detail metadata delivery：列表與詳情共用同一本地化 formatter，詳情顯示
  可讀日期／時間及現有地點／時長，缺少 optional 值時省略。Writer focused 64/64、analyze／formatter與 Main
  review通過；delivery PR只使用一次 change-selected hosted Flutter gate，未使用Domain／emulator／staging／harness。
- TASK-144 production-shaped fake demo 已由 PR #171 合併；development fake mode直接重用正式賽事／出席／帳號／
  Officer報表 widgets，並提供 deterministic fictional scenarios，不需帳號、Secret、staging或網路。
- TASK-145 三個 delivery unit 已由 PR #172 合併為 `c4016dce924a1fa3e1edfaab7b9581ec968e04eb`：Flutter 視覺與
  refresh feedback、持久通知讀取模型／中心、Officer publishing／outbox／device/deep-link repository foundation。
  Final hosted run 32559518555 通過；未執行 deployment、staging、Secret/IAM、真實 provider／資料操作。Production、
  真實通知、release signing 與 stores 仍未授權。
- TASK-146 已啟動為第一個新流程 L2 pilot：將既有通知中心接入正式 Flutter 首頁、badge、session/capability 與
  offline cache lifecycle。範圍限 Flutter repository integration；不改 backend/schema，不使用 emulator/staging/provider。
- PR #180 已合併為 `cd49e2038b1d804b3e3c729c510eb8c34df59efb`，完成 Google 登入、LINE／Google 跨 provider
  登入方式連結與陌生登入追認，以及 Web／Mobile／Flutter release-readiness plumbing；合併前 12 項 hosted checks
  與獨立 Web/Auth/DB、Flutter Auth review 均通過，且沒有 schema migration。該 PR 當時不代表任何外部 rollout；
  後續 TASK-157 才完成隔離 staging deployment 與真 provider smoke。Production deployment／provider publishing與
  iOS signing仍未完成，且 OAuth/provider、Secret/IAM與production部署持續受Owner gate約束。
- TASK-157 已完成 fictional staging rollout 與 real-provider smoke。Staging DB 為 revision `0008`；shared primary
  External／Testing provider沿用既有Web server audience與Android debug/staging client，runtime/data維持在
  `ntubtob-mobile-staging`。Android emulator 已驗證 LINE Person 連結 Google、fresh server 雙 provider 狀態、LINE session
  登出失效及 Google 登入同一 Person；PR #201 的 accessibility status 修正與 hosted full gate均通過。未修改 OAuth
  client／provider設定，未觸及production；production deployment／provider publishing／client promotion仍是未來Owner gate。
- TASK-158 已由 PR #189 合併 Mobile API／Flutter Event read vertical slice：active Person 只看 immutable invitee snapshot
  `included=true` 的 published／cancelled、non-ended Event 與 ordered Activity；linked Game 仍受既有 Game scope 限制。
- TASK-159 Web Portal read parity 已由 PR #190 合併，重用同一 repository authorization 與公開 projection；列表、詳情、
  timeline、empty/error/cancelled presentation已完成，不包含 Event write、attendance、notification、schema 或 deploy。

## 已確認的 production 狀態

### 資料庫與身分資料

- PostgreSQL schema：`ntubtob`。
- Alembic revision：`0009_event_management_writes`。
- Phase A 建立 portal-data schema boundary；新表採 RLS enabled／zero-policy 的 fail-closed 基準。
- Phase B 完成 deterministic backfill：197 People／Member links、56 LINE identities、56 active `team_player`、309 筆
  append-only audits；當時 strict post-check 無 orphan、duplicate 或 qualification drift。
- Phase C identity lifecycle、Person-based attendance、pending review conversation 與 audit actions 已建立。
- 2026-08-09 完成管理與隊員啟用：先啟用 exact-two allowlisted administrators，再啟用其餘 54 位 existing
  reliably linked team players；兩次 mutation 均以精確 cohort、單一 transaction、post-check 與 retry verification 完成。
- 管理權限目前仍以 Web Portal runtime allowlist 為準；Person 的 portal access level 尚未取代 allowlist。

### Runtime 與服務

- Web Portal、LINE webhook、notify cron 的 Phase C flag 已啟用，freeze 已解除。2026-08-27 唯讀 inventory 證實
  Web Portal identity maintenance flag 已為 true；production identity-link plain configuration仍不完整／未啟用。
- 已確認的 production revisions：
  - Web Portal：`web-portal-00054-rtp`，100% traffic；image tag對應repository commit `0d6efacac2f20fe1ff66f1aa9ae84fd888ab0961`。
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
- 一般 Git 操作具有 Owner standing authorization。Owner另於2026-08-30明確授權各branch push至exact origin
  `https://github.com/r06521541/NTUBTOB-management-system.git`，直到task開始前另行限制或撤回；此授權不包含
  PR merge、production deployment、production DB mutation、Secret／IAM／Scheduler／cloud resource變更或真實通知。

## 尚未驗證與已知限制

- 啟用 56 位 Person 後尚未由 Owner 做一次一般瀏覽器與 LINE in-app browser 的人工登入／頁面 smoke；production
  post-check 已證明資料狀態，但不等於使用者端完整操作驗收。
- 自然 Scheduler 執行與低流量環境的長期 observation 不足；不得以缺少 error log 推定所有通知情境都已覆蓋。
- Identity maintenance 已在live Web Portal為true；TASK-160的新管理UX尚待本次production deployment與post-check。
- People role 尚未取代 runtime admin allowlist；officer／admin 的正式持久化權限切換仍屬 Phase D 之後工作。
- Event／Activity schema、principal-scoped read及create/edit/publish/cancel已成為production功能；TASK-168已完成
  Event／一般Activity三態出席與linked Game五態single-source repository整合，但尚未部署。通知及guest-player管理規則仍未成為production功能。
- Google OAuth 與 LINE／Google identity linking/recovery 已在 PR #180 完成 repository implementation，TASK-157亦已
  完成隔離staging deployment與單一fictional tester real-provider smoke。這不驗證或啟用production；primary provider
  publishing、production runtime binding／deployment、Android debug/staging client退役或遷移及production smoke仍需
  未來Owner明確核准。Apple 登入仍未實作。
- Attendance 首次載入可能受 Cloud Run／資料庫 cold path 影響；現階段接受延遲，後續應先量測再改架構。

## 下一階段候選方向

### P2：Event 與多元活動

- 將 Event／Activity、複合行程、非聯盟比賽、聚餐、旅遊與 guest player 從 Demo 收斂為正式 domain design。
- 在 schema 前先定案活動參與資格、幹部建立權限、邀請快照與資格異動語意。

### P3：工程與維運健全性

- 將文字 artifact checksum 統一為 canonical LF helper，補 LF／CRLF CI regression。
- CI change classifier對docs/archive與核准的repository bootstrap wrapper使用quick-only；classifier／workflow、未知路徑、
  schema與shared boundary仍fail-safe升級。
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
