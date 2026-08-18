# 現行決策

本文件只保存目前仍規範未來行為的決策。DEC-001～075 原始紀錄保留於
`archive/governance/DECISIONS-001-075.md`，只能證明當時授權與執行事實，不自動授權現在的操作。

## DEC-076：一般 Git 工作流程授權

- 狀態：`active`
- 生效：2026-08-09
- 來源：DEC-066、DEC-073、DEC-075
- Supersedes：DEC-026、DEC-066、DEC-073、DEC-075
- 決策：Work／Codex可在 task 範圍內自行完成 branch、commit、push、PR、CI 查驗、ready、修正、squash merge、
  同步 `main` 與清理 branch，不需逐次請示。
- 前提：Work 已驗收實際 diff，required CI 成功，且沒有 blocker、範圍擴張或 production 副作用。
- 排除：production deployment／DB、Secret／IAM／Scheduler／cloud resource、真實通知及重大產品／架構變更。

## DEC-077：TASK、Push 與 PR 分離

- 狀態：`active`
- 生效：2026-08-09
- 來源：DEC-073、DEC-075
- Supersedes：DEC-004、DEC-011、DEC-073、DEC-075
- 決策：TASK 是工作與決策單位，push 是 checkpoint／交棒，PR 是整合 delivery unit；三者不必一對一。
- TASK 分為 `planning`、`work_package`、`delivery`；同一 `delivery_group` 原則上只有一個 ready PR 與一次 final CI。
- 純 coordination 狀態不單獨 commit／PR；階段完成後由 closeout 摘要並封存歷史文件。

## DEC-078：Production 操作批准邊界

- 狀態：`active`
- 生效：2026-08-09
- 來源：歷次 production runbooks／Owner 授權邊界
- Supersedes：無；本項整併持續有效的安全邊界
- 決策：production deployment、production DB DDL／DML、不可逆資料操作、Secret／IAM／Scheduler／cloud resource
  變更與真實 LINE／Discord 通知，仍需 Owner 對精確 target、範圍與 rollback 個別批准。
- 流程：read-only discovery → Owner 精確批准 → 單次 execution → post-check。
- 不確定結果：工具取消、網路中斷或輸出不明時不得重跑 mutation；先查外部狀態或走唯讀 recovery diagnostic。

## DEC-079：Member、Person 與登入身分分離

- 狀態：`active`
- 生效：2026-08-09
- 來源：DEC-068、DEC-072、DEC-074
- Supersedes：DEC-068、DEC-072 中相同主題的現行規範
- Member 是依校友名冊維護的永久正式成員；每位 Member 對應一個 Person，但 Member 本身不等於登入帳號。
- Person 是產品中的人格主體，可具有多個 auth identities；同一 provider 可連多個不同帳號，但 provider＋subject
  必須全域唯一。
- 新 LINE identity 未配對前為 pending candidate，不因 display name／頭貼自動配對。
- 經可靠 LINE 關係配對為 Member 時，預設授予 active `team_player`；LINE 不是資格持續存在的永久必要條件。
- `display_name` 可由本人使用；Member 正式姓名以 Member 為準，非 Member 可有 `formal_name`；admin note 僅管理者可見。

## DEC-080：Person 狀態、identity 狀態與 qualification 分離

- 狀態：`active`
- 生效：2026-08-09
- 來源：DEC-072
- Supersedes：DEC-072 中相同主題的現行規範
- Person 的 `active／inactive／disabled／blocked` 管整個人的 portal 參與狀態；UI 將 `disabled` 描述為「暫停參與」。
- Identity 的 linked／ignored／rejected／disabled 等狀態只管理單一登入方式，不自動推導 Person blocked／disabled。
- Qualification 管活動能力，與 portal access 分離；允許 active 但無 qualification 的純檢視 Person。
- `revoked → active` 必須是明確恢復操作，不可因重新配對暗中恢復。

## DEC-081：資格與既有比賽出席

- 狀態：`active`
- 生效：2026-08-09
- 來源：DEC-072
- Supersedes：DEC-072 中相同主題的現行規範
- `team_player` 只授予正式 Member；有效 `guest_player` 可回覆既有比賽出席。
- Guest-player 資格使用 Asia/Taipei 日期、必須有限期、單次最長五年，以比賽開始時間判定有效性。
- 撤銷資格不刪除歷史；日後不合資格的回覆不計入有效名單。
- Active affiliate／staff／guest-player 可檢視既有賽程；活動參與資格仍待 Event 正式設計，不由本條推定。

## DEC-082：管理權限仍以 runtime allowlist 為準

- 狀態：`active`
- 生效：2026-08-09
- 來源：DEC-072、DEC-074
- Supersedes：DEC-072 中相同主題的現行規範
- Production Web Portal admin authority 目前只依 `WEB_PORTAL_ADMIN_MEMBER_IDS` runtime allowlist。
- Person 的 access level 尚未取代 allowlist；affiliate 未來可以成為 admin，但必須經明確、可稽核的 cutover。
- 持久化角色切換必須保護 last-admin concurrency、self-lockout 與 audit atomicity。

## DEC-083：Phase C 已完成

- 狀態：`active_fact`
- 生效：2026-08-09
- 來源：DEC-067、DEC-069、DEC-071～074、Phase C closeout
- Supersedes：DEC-067、DEC-069、DEC-071～074 的階段狀態敘述
- Production revision 為 `0004_phase_c_identity_lifecycle`；三個直接服務已啟用 Phase C、freeze 已解除。
- 197 位 Member／Person、56 組可靠 LINE identity／active team-player 關係存在。
- 2 位 allowlist 管理者及其餘 54 位可靠連結隊員的 Person 均已 active；最終 post-check drift 為 0。
- Identity maintenance flag 仍為 false；pending identity 正式管理流程屬後續工作。
- Phase C schema／audit 不以 destructive downgrade 作一般 rollback；語意錯誤採 forward compensation。

## DEC-084：Web Portal 產品與登入方向

- 狀態：`active`
- 生效：2026-08-09
- 來源：DEC-057～063
- Supersedes：DEC-057～063 中相同主題的現行規範
- Portal 採 mobile-first、隊徽深藍／中性灰；綠色保留 LINE／成功，紅色保留警示與破壞性操作。
- LINE Login 必須維持 session／state binding；手機一般瀏覽器不保證可喚起 LINE App，應引導 LINE 使用者在 LINE
  in-app browser 開啟。電腦可使用 LINE 提供的 QR／帳號登入。
- Google／Apple 目前僅 prototype UI，不宣稱已串接 OAuth。
- 登入後目的地曾有 production 未完全解決的回首頁情況；不得以降低 state／CSRF 邊界換取 redirect 便利。

## DEC-085：通知渠道與 LINE Notify 棄用

- 狀態：`active`
- 生效：2026-08-09
- 來源：Owner 對現行通知渠道的澄清
- Supersedes：任何將 legacy LINE Notify 視為現行通知依賴的舊假設
- 決策：已棄用的是「LINE Notify」產品、API 與 legacy `line_notify_tokens`；不得維護或建立新的 LINE Notify
  token 流程。
- 保留並仍可使用的是「LINE Official Account／Messaging API」，包括既有 LINE Login／webhook／官方帳號訊息
  能力；其 Channel Access Token／Channel Secret 必須透過現行 Secret Manager boundary 管理。
- Discord 是另一個獨立通知渠道。新功能必須依實際 caller 明確選擇 Discord 或 LINE Messaging API，不得把
  LINE Notify、LINE Login、LINE webhook 與官方帳號訊息混稱為同一功能。
- 真實通知、人工 invoke 或 broadcast 仍需 Owner 明確批准。

## DEC-086：Event／Activity 尚未定案

- 狀態：`active_planning`
- 生效：2026-08-09
- 來源：`docs/planning/EVENT_MANAGEMENT_PLAN.md` 與 Owner 討論
- Supersedes：無
- 多元 Event、Activity、複合旅程、非聯盟比賽、聚餐、旅遊、交通住宿與 guest-player eligibility 已有 Demo／規劃。
- 幹部建立活動、邀請快照、資格異動、同行者／affiliate 參與與多場比賽隸屬旅程等規則尚未成為 production contract。
- 不因 Demo 或 planning 文件直接建立 schema、migration、production route 或權限。

## DEC-087：最小充分 CI 與 canonical checksum

- 狀態：`active`
- 生效：2026-08-09
- 來源：DEC-073、DEC-075
- Supersedes：DEC-073、DEC-075 的 CI／checksum 流程規範
- 純文件走快速 gate；單一服務跑受影響 suite；shared library 跑直接 callers；database／受控 SQL 才跑
  PostgreSQL 15／16 matrix。
- Checksum-locked text artifact 先將 CRLF 正規化為 LF，再計算 SHA-256；binary 才 hash raw bytes。
- 新的 checksum workflow 必須共用 repository helper；在 helper 尚未統一前，只能沿用該 artifact 已存在且有測試的
  generator／verifier，不得用 `Get-FileHash` 等 raw-byte 工具重產文字 checksum。

## DEC-088：「下一個task」授權前一任務收尾

- 狀態：`active`
- 生效：2026-08-10
- 來源：Owner 明確長期授權
- Supersedes：無
- Owner 說「下一個task」時，同時授權 Work 完成前一 task 範圍內尚未完成的驗收、文件收斂、commit、push、PR、
  hosted CI 查驗、必要修正與 squash merge，再開始界定下一個 task。
- 此語句不授權部署、production DB DDL／DML、Secret／IAM／Scheduler／cloud resource 變更、真實通知或其他原本需
  Owner 個別批准的操作；若前一 task 出現 blocker、範圍擴張或 required CI 失敗，仍須依既有流程停止或補正。

## DEC-089：Game 資訊唯讀與 session-only 守位試排

- 狀態：`active`
- 生效：2026-08-10
- 來源：Owner 對下一波 Officer／Admin Game command center 的明確決定
- Supersedes：無
- 下一波 Game command center 在 schema 完全不動的前提下，正式 Game、Roster 與 Attendance 管理資訊全面唯讀；
  不建立、編輯、取消、改期或代改出席，也不發送通知。
- 幹部試排守位是核心能力，但只存在 browser session，不寫入 database、server session、cache、audit、log 或
  notification。未來需要長期保存與維護的陣容資料只有正式出賽名單；試排本身永不持久化。
- 粗排提供教練、投手、捕手、內野、外野；教練也是 Roster 中的 Member，可 player-coach。細排提供 P、C、
  1B、2B、3B、SS、LF、CF、RF、DH，並使用具 accessible fallback 的棒球場視覺。
- Production admin authority仍由 runtime allowlist決定。Person `officer` 在正式全站 cutover 前，只能透過明確的
  bounded Game route bridge取得本批 Game command center／insight／lineup權限，不得因此取得其他管理能力。

## DEC-090：Fictional local demo 與 cloud-derived preview 分離

- 狀態：`active`
- 生效：2026-08-11
- 來源：Owner 對 TASK-098 localhost 驗收與後續 UI 作業模式的明確決定
- Supersedes：無
- Owner 日常 UI／角色／導覽驗收以 deterministic fictional local demo 為主要工作模式；該模式必須可安全 seed、reset、
  cleanup，固定 revision／local database／fixture state，且不得連 Supabase、外部服務或 production。
- Fictional demo 與 cloud-derived production-shaped preview 是兩條互斥 workflow。前者可在 exact local fictional DB
  演練受控管理 mutation；後者只讀且所有 Portal mutation POST 持續 fail closed。不得混合兩者資料或用 demo gate
  放寬 production／cloud-derived preview authorization。
- Production Admin 仍由 runtime allowlist 決定。Allowlist Admin 可透過受稽核 UI 指派 `basic ↔ officer`，但 UI
  不得建立／解除 Admin；Officer 仍只取得明確 bounded capabilities。

## DEC-091：Main Work 是多領域 Work 的唯一核心協調節點

- 狀態：`active`
- 生效：2026-08-18
- 來源：Owner 對多個決策核心與未來擴充更多 Work session 的明確決定
- Supersedes：無
- 決策：專案可依 Flutter、Web、data 等領域建立不限數量的 Domain Work；Domain Work 在已核准領域與 task 內具有
  規劃、低風險次決策、派工與 task 內補正自主權。Main Work 保持唯一全域核心，統一管理 TASK／DEC 編號、跨領域
  契約、依賴、衝突、final PR／merge／deployment 與最終驗收。
- Invariants：新增 Domain Work 前必須由 Main Work 登記邊界；跨端 API、auth、schema、shared model、通知、production、
  Secret、IAM、cloud、正式資料與 release 必須升級。Domain Work 完成正式 task 後交回 Main Work，未收到
  `next_task_assigned` 不自行開始下一個正式 implementation task。
- Non-goals：不要求領域內每個 UI／元件／測試小步驟逐次請示，也不允許 Domain Work 各自建立互相競爭的全域治理
  來源或編號空間。

## 決策維護方式

- DEC 使用單一連續編號；本檔目前為 `DEC-076～091`，下一個新決策從 `DEC-092` 開始。Archive 中的編號不重用、
  不重編。
- 只有跨 task 持續生效的產品、架構、授權或安全決策才新增 DEC。單次 task／PR／部署核准與執行結果不升格為 DEC。
- 不改語意的澄清更新原 DEC 並記錄修訂日期；語意改變時新增 DEC，以 `supersedes` 指向舊項。
- 被取代、完成後只剩歷史價值或與其他 active decisions 重疊時，由 Work 批次整併並移入 append-only history。
- Active decisions 不設數量上限；完成一個 phase、重大階段開始前、出現重複／衝突或 Owner／agent 覺得難以閱讀
  時，Work 主動整理。若必要內容無法清楚表達，先向 Owner 回報，不自行刪減安全或產品規則。

## 衝突處理

優先序：Owner 最新明確指示 → active task 的明確安全例外 → `HANDOFF.yaml` → 本文件／`COLLABORATION.md`／
`AGENTS.md` → archive 歷史。若 active task 想採更嚴格流程，必須寫明理由、範圍與結束條件；不得用歷史文件降低
目前安全邊界。
