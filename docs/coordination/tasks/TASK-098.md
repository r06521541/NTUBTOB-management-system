# TASK-098：Schema-neutral Game command center, attendance insights and lineup lab

task_type: delivery
delivery_group: phase-d-schema-neutral-game-command-center
requires_independent_pr: true
status: ready_for_codex
owner: work
codex: codex

## 使用者價值

在完全不變更 schema 與正式 Game 資料的前提下，讓 Officer／Admin 以手機或桌面快速掌握近期比賽、Roster、
出席回覆與待跟進狀況，並可在瀏覽器 session 內試排粗略分組或各守位陣容。試排不保存、不通知、不影響正式
Roster；未來需要長期維護的陣容資料只有出賽名單。

## 固定邊界

- Database revision 固定為 `0004_phase_c_identity_lifecycle`；不得新增／修改／刪除 table、column、constraint、
  index、trigger、view、function、enum 或 migration。
- Game 資訊全面唯讀：不得建立、編輯、取消、改期、還原 crawler 值，亦不得修改 invitation、cancellation、
  Roster、Attendance、Person 或 Qualification。
- 隊員既有「回覆自己的出席狀態」維持原行為；Officer／Admin 不得代改或人工修正。
- 不發送 LINE／Discord，不建立通知 outbox，不呼叫 crawler／weather 或其他外部服務。
- 不建立 Event／Activity production domain，不把 Demo/session state 誤稱為正式資料。
- 本 task 只實作、測試、commit、push、PR 與 CI；不部署、不操作 production、Secret、IAM、Scheduler 或正式資料。

## Scope

### 1. Bounded Game management authority

- Production admin 仍只由 `WEB_PORTAL_ADMIN_MEMBER_IDS` runtime allowlist 決定；Person `admin` 不得取代或繞過
  allowlist。
- Active、已確認 Person 且 access level 為 `officer` 者，只能在本 task 新增的 Game command center／insights／
  lineup routes 取得 `MANAGE_EVENTS`／`VIEW_TEAM_ATTENDANCE`／`MANAGE_GAME_DAY` 的 bounded access。
- 不得因此開放既有 Person、pending identity、qualification、role assignment、notification confirm/send 或 audit
  management routes；現有 production principal resolver 與其他管理 route 行為保持不變。
- 每個 request 重新載入 Person status／access；pending、inactive、disabled、blocked、未知或矛盾狀態 fail closed。
- Basic 直接存取所有 `/manage/games...` routes 必須拒絕；UI 隱藏不可取代 server-side authorization。

### 2. 正式 Game command center 與洞察

建議 routes：

- `/manage/games`
- `/manage/games/<int:game_id>`
- `/manage/game-insights`
- `/manage/games/<int:game_id>/lineup-lab`

提供：

- 未來／近期／過去／取消比賽篩選，並顯示日期、對手、主客場、球場、邀請與取消狀態。
- 各場既有 Attendance 語意的出席、晚到、早退、不出席與目前未回覆分類及低敏名單。
- 依現有 read model 顯示 Roster 與 `team_player`／`guest_player` 維度、empty／error／資料不完整狀態。
- 最近比賽的已記錄回覆趨勢、未來 7／30 天比賽數、取消比賽數及資料更新時間。
- 指標必須依現有資料誠實命名；沒有 per-Game invitee snapshot 時不得宣稱精確歷史邀請回覆率或歷史 Roster。
- 不提供打擊率、防禦率、勝率、交通、裝備、守位能力或其他沒有正式資料來源的洞察。
- 可複製低敏待回覆名單；若提供 CSV，只允許顯示名稱、qualification 類別與 reply 類別，並防止 spreadsheet
  formula injection。不得輸出 provider subject、電話、admin note、Secret 或認證資訊。
- Command center 不得以一小時舊 cache 假裝即時洞察；若使用 bounded cache，須顯示資料時間與 TTL，且不得跨
  使用者洩漏資料。

### 3. Session-only lineup lab

- 候選人只來自該 Game 目前 server-authorized 的 Roster/read model；不得輸入任意姓名或加入名單外 Person。
- 所有試排只保存在 browser `sessionStorage`；禁止 database、server-side session persistence、`localStorage`、
  shared cache、log、audit、notification 或外部 request。
- State 只保存 bounded Game／Person 或 Member identifiers，不保存 provider subject、private note 或額外個資。
- 重新整理可保留；登出、local-preview identity 切換或關閉分頁後清除。重新載入時重新驗證目前 Roster；已不在
  名單者標示並要求移除，不得靜默當成正式成員。
- 試排不影響 Attendance、Roster、insight、CSV、統計或任何正式 caller；頁面不得出現「儲存正式先發」或
  「發送陣容」等誤導操作。

#### 粗排模式

- 分組為：教練、投手、捕手、內野、外野、未安排。
- 各組可放多人；教練必須是目前 Roster 中的 Member 成員。
- 允許 player-coach：同一人可同時是教練與一個球員分類；除教練外不可同時存在多個球員分類。
- 支援點選／選單；desktop 可額外支援 drag-and-drop，但 mobile、keyboard 與 screen reader 不得依賴拖曳。
- 可獨立重設粗排。

#### 細排模式

- 位置為 P、C、1B、2B、3B、SS、LF、CF、RF、DH、教練及未安排／板凳。
- 以 repository-native HTML／CSS／SVG 顯示棒球場：本壘、投手丘、三壘包、內野與外野區，各守位位於合理位置；
  DH 顯示於球場側邊，不錯誤表示為防守位置。
- P、C、1B、2B、3B、SS、LF、CF、RF、DH 各一個主要槽位；同一球員不可同時佔兩個正式球員位置，但可兼任
  教練。
- 放入已有人員的位置時須明確交換或確認取代，不得靜默遺失原人員。
- 視覺球場與 accessible list／select 必須共用同一 client-side state；手機可先選球員再選守位。
- 粗排與細排保存兩份互不覆蓋的 session draft；模式切換不得猜測模糊轉換，例如「內野」不可自動變成 SS。
- 可獨立重設細排或清除全部；可複製文字摘要與提供 print-friendly 顯示，但不得傳送或持久化。

### 4. Local preview parity

- `/local-preview/login` 可用假名化 basic／officer／admin 身份讀取與 production 相同的 command center、insights、
  lineup route／template／repository contract。
- Production-shaped preview 仍為資料庫唯讀；lineup 全在 `sessionStorage`，不得為它放寬 preview POST boundary。
- Preview importer 與 bundle revision 維持 `0004`；優先沿用現有六表固定 export contract。若 UI 需要未匯出欄位，
  應縮減 UI，不得擴張 source export 或讀取 Secret／credential。
- Local preview 與 production 的承諾只涵蓋 read UI／route/template 及 client-side lineup；真實 LINE Login、
  production admin allowlist、正式 mutation 與通知不宣稱一致。

## 明確非目標

- Game create／edit／cancel／reschedule、crawler override／restore、Roster snapshot／override、Attendance 人工修正。
- Persistent lineup、先發、打序、局數輪替、球員守位能力、球衣背號或球員表現統計。
- Admin allowlist cutover、全站 persistent officer rollout、正式 officer 指派或其他管理 capability 啟用。
- Notification preview/send、LINE／Discord、Event／Activity、Google／Apple OAuth。
- Schema／migration、production deployment、production data、Secret／IAM／Scheduler／cloud resource 操作。

## 驗收條件

- Basic／Officer／Admin allow/deny matrix 同時覆蓋 route 與 domain/helper；bounded officer 不得存取既有非 Game
  management routes。
- 每個 request 重新驗證 actor 與 Game；missing Game、malformed ID、unknown status/access、取消 Game 新試排均
  fail closed，且不得先建立 client/server side effect。
- Insight 計算、排序、empty/error state、資料時間、qualification 分組及不精確指標文案有離線測試。
- Lineup state 使用 `sessionStorage` 而非 `localStorage`；粗／細模式隔離、player-coach、重複守位、交換／取代、
  reset、logout／identity-switch cleanup 與 stale-roster 處理均受測。
- 細排同時具棒球場視覺與 accessible list/select；375px mobile、keyboard focus、touch target 與無 external CDN
  contract 通過。
- Local preview 可 render 三種角色的 read pages 與 lineup lab，且現有 database mutation POST 仍全部拒絕。
- 測試不得以 mock 隱藏任何 production repository write；須明確證明 lineup 操作不呼叫 SQL、repository mutation、
  notifier、crawler 或 external HTTP。

## 最小充分驗證

- Web Portal 完整 offline unittest suite及新增 route/template/static contract tests。
- 受影響 Python `py_compile`、Black 24.4.2／isort 5.13.2逐檔檢查、`git diff --check`、clean status。
- 使用 bundled Python執行本機驗證；hosted Python 3.10提供 final compatibility evidence。
- 本 task 不改 schema／migration／model／受控 SQL，預設不需要 PostgreSQL 15／16 matrix；若實際 diff 觸及這些
  邊界，Codex 必須停止並交回 Work，不得自行擴張。
- Browser QA 至少涵蓋 desktop 與約 390px mobile 的 command center及細排球場；不得連 production或真實 LINE。

## Execution checkpoint

Codex 開始實作前須回報五行 checkpoint：目標、核心檔案、關鍵 invariant、最小充分測試、歧義／blocker。
若發現現有 read model不足以誠實產生某指標或 Roster，縮減該項並交回 Work，不得以 schema、假資料或錯誤命名繞過。
