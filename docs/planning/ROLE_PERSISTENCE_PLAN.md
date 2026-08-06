# Web Portal 人員、權限、資格與多類型 Event 持久化藍圖

狀態：`owner_approved_design_direction`

本文記錄 Owner 於 TASK-047 核准的正式概念模型。它取代先前將 role/status 直接放在 `members`、並把 affiliate 當單一角色的提案。本文仍不授權 schema、migration、production data 或 deployment 操作。

## 1. 三個必須分離的資料軸

| 資料軸 | 回答的問題 | 正式主體 |
| --- | --- | --- |
| Person | 這個自然人是誰、能否進 Portal、具何種管理權限？ | `people` |
| Member | 是否列入球隊永久正式校友名冊？ | `members`，0..1 對應 Person |
| Qualification | 目前以什麼資格參與球隊或活動？ | `person_qualifications`，一人多值 |

Member、access level、qualification 不互相推導：

- Member 可以 inactive，但永久保留於正式校友名冊；每屆新增，不因離隊或不活躍而刪除。
- 非 Member 的 affiliate、guest player 或 staff 仍可成為 officer/admin。
- officer/admin 不自動取得 `team_player`，也不因此自動列入球員名單或統計。
- `affiliate` 是 qualification，不是 access level。

## 2. 核准概念模型

### 2.1 `people`

自然人基本單位，建議欄位：

- `id`
- 最小顯示名稱
- `portal_access_level`：`basic`、`officer`、`admin`
- `portal_status`：`pending`、`active`、`disabled`、`inactive`、`blocked`
- 建立／更新時間與 optimistic version

狀態語意：

| 狀態 | 語意 | Portal access |
| --- | --- | --- |
| pending | 尚待管理員核可／匹配 | 僅等待核可流程 |
| active | 可依 access level 與 qualifications 使用 | 允許 |
| disabled | 暫停使用，可由授權管理員恢復 | 拒絕受保護內容 |
| inactive | 不活躍但保留歷史與資格資料 | 預設拒絕；恢復需明確 mutation |
| blocked | 明確封鎖，不可由一般配對流程恢復 | 拒絕；需較高風險復原流程 |

未知、NULL 或畸形 access/status 一律 fail closed。`admin` 暫定繼承 `officer` capabilities；access level 不寫入 client session，每次 request 從 Person 最小 access projection 解析。

### 2.2 `members`

永久正式校友名冊：

- 保留現有 Member identity 與歷史關聯。
- 新增 nullable unique `person_id` FK → `people.id`，形成 Member → Person 0..1；過渡期允許尚未匹配的舊 Member。
- 每屆正式隊員新增 Member record；inactive 不刪除 Member。
- Member 不保存 Portal access level/status，也不作登入主體。

### 2.3 `auth_identities`

登入身分多對一 Person：

- `person_id` nullable FK；pending identity 尚未配對時可為 NULL。
- `provider`、`provider_subject`，unique `(provider, provider_subject)`。
- 同一 Person 可綁同 provider 的多個帳號，也可跨 LINE／未來 Google／Apple。
- 保存 provider 所需最小 metadata 與 identity status，不保存 access level。

管理員處理 pending identity 時只能選擇：匹配既有 Person/Member、建立 non-member Person，或 blocked。不得由 LINE 暱稱/display name 自動推測 Member、資格或 access。

### 2.4 `person_qualifications`

持久多值資格池，第一版固定值：

- `team_player`：正式球隊球員資格
- `guest_player`：客座／友誼賽球員
- `affiliate`：關係人／校友／支援者但非正式球員
- `staff`：球隊工作人員

建議 unique `(person_id, qualification)`，並保存 granted/revoked metadata 或有效期間。取消資格不可刪除歷史 audit。Qualification 不授予 officer/admin；access level 也不授予 qualification。

### 2.5 Event、邀請與出席

- `events`：活動容器，含類型、標題、起訖、draft/published/cancelled、建立者與版本。
- `activities`：有序子行程，類型含 game/meal/transport/lodging/gathering/other。
- Game activity 可連既有 `games.id`；league/manual source ownership 必須明確，crawler 不得覆蓋 manual game。
- Event draft 保存 eligibility rules，例如邀請 `team_player`、`guest_player`、`staff` 的聯集／限制。
- **publish transaction 依當下 qualifications 自動產生 `event_invitees` 快照**；發布後資格變化不暗中改寫既有邀請。
- `event_invitees` 保存 person、來源規則/qualification、included/excluded 與 snapshot time；另允許 individual/manual include/exclude override，且必須 audit actor/reason。
- 整體 Event 回覆與 Activity override 分層保存；Activity override 只記與整體不同的例外。
- Attendance、roster、statistics 必須分別標示 `team_player` 與 `guest_player`；guest 不得計入正式隊員統計，除非報表明確選擇 guest 維度。

發布後新增邀請人不應自動發通知；重新計算 invitees 必須是明確、可預覽、有差異清單與 audit 的操作。

## 3. 現況與相容邊界

- 現在 production session 是 LINE `user_id` + `member_id`；未來應逐步改為 server-side identity → Person，不能一次破壞既有登入。
- `WEB_PORTAL_ADMIN_MEMBER_IDS` 目前是唯一 production admin source。過渡期可由 Member → Person mapping 對應 break-glass admin，但不可繞過 Person disabled/inactive/blocked。
- 現有 code 的 `member` role 是 access policy 名稱；migration 後應改稱 `basic`，避免與永久名冊 Member 衝突。相容 adapter 可暫時把 `basic` 映射至舊 policy `member`，直到 callers 全部更新。
- 現有 `line_users.ignored` 不是 Person status；舊配對資料需可重跑地搬到 auth identity，不可直接把 ignored 猜成 blocked。
- 現有 Game/game attendance 在相容期保持真實來源；Event projection 與新 attendance 切換須另有契約。

## 4. Principal 與 route 安全流程

1. 從 server session 取得有效 auth identity reference，不信任 client 提供 Person/access/qualification。
2. request-time 讀 identity + Person 最小 projection。
3. identity 未配對或 Person pending：只進等待核可；disabled/inactive/blocked/未知：拒絕。
4. active Person 的 `portal_access_level` 交由集中 capability policy；未知 level 拒絕。
5. Event eligibility/roster 另查 qualifications 或 invitee snapshot，不能從 access level 推導。
6. UI 隱藏只是 UX；每個 read/mutation route 在資料讀取或副作用前重新驗 capability、status 與 event scope。

## 5. Migration 與 rollout

### Phase 0：工具與 local contract

- 採版本化 migration 工具；Supabase SQL Editor 不作唯一歷史。
- Local prototype 透過單一 `TeamPortalRepository` 與集中虛構 fixtures 提供 Person/Member/identity/qualification/Event/invitee/reply，不逐表 mock。
- 正式 persistence 用 ephemeral PostgreSQL 或 Supabase local 從空 schema 跑 migration，驗證 FK/unique/check/index、transaction、concurrency、backfill idempotency 與 rollback rehearsal。
- 同一組 repository contract tests 跑 in-memory 與 PostgreSQL implementations。

### Phase 1：expand schema

- 同一 migration series 新增 people、Member person FK、auth identities、qualifications、access audit、Event/Activity/eligibility/invitees/attendance structures。
- 欄位先 nullable、寫入關閉；constraints 可先 NOT VALID 後 validate，先在近似 production volume 評估 lock/time。
- 舊 revisions 必須仍可使用既有 Member、LineUser、Game 與 attendance。

### Phase 2：identity/person dual-read

- 依既有 LineUser/Member 建可重跑 Person 與 auth identity mapping；歧義資料列入報告，不自動合併自然人。
- 既有 Member 對應 Person 預設 active/basic；admin allowlist 對應 Person 經核對後設 admin。
- 舊 session 可經 server-side adapter 找 Person；新 session 不保存 access/qualification。
- 所有 active revisions 理解 Person status 後，才可啟用 status mutation。

### Phase 3：qualification 與 Event backfill

- `team_player` 名單必須由 Owner 核准規則/資料來源回填，不能以 Member、active、出席紀錄或 access level自行推測。
- 既有 Game 建 idempotent Event/Activity wrapper；source 不明者列例外，不猜 league/manual。
- Invitee snapshot 只對新 publish 啟用；歷史賽事不事後虛構邀請快照。

### Phase 4：受控 mutation

- 先上 identity matching、Person access/status、qualification mutation domain + audit，再上 admin UI。
- Event draft → preview eligibility → publish transaction → invitee snapshot；individual overrides 顯示差異與 reason。
- 發布與通知是兩個操作；新 attendance 是否同步 legacy game reply，需獨立 compatibility contract。

### Phase 5：contract

- 至少兩位已驗證 active admins、break-glass 演練成功後，admin allowlist 才降為緊急用途。
- 所有登入/provider、Event、attendance、roster、statistics、crawler、webhook、排程與通知 callers 均完成相容驗證後，才停止 legacy paths；drop 永遠另案。

## 6. Rollback

- Expand schema 保留；不以 drop table/column 緊急 rollback。
- 一旦使用 disabled/inactive/blocked，禁止回到不理解 Person status 的 revision，否則被限制者可能恢復存取。
- 一旦 Event 新寫入或 manual source 啟用，rollback revision 必須理解 source ownership；否則停止 mutation並維持 read-only。
- Invitee snapshot 不因 rollback 或 qualification 改變而重算；錯誤邀請以 audited override 修正。
- 錯誤 access/status/qualification 以反向 mutation修正並 append audit，不刪歷史。

## 7. 管理操作與稽核

- 只有 active admin 且具相應 capability 可匹配 identity、建立 non-member Person、blocked identity、變更 access/status/qualification。
- POST + session-bound CSRF + 固定值 + reason + unique request ID；actor/target request-time reload，更新與 append-only audit 同 transaction。
- 不得自行移除 admin；不可移除最後一位 active admin。跨列規則以 transaction-level singleton/advisory lock 後計數。
- blocked 的復原權限應高於一般 pending matching，且要求二次確認與 reason。
- Portal admin 不自動獲得 Secret、deployment、IAM、DDL 或不可逆 production data 權限。
- Mutation 不自動發 LINE/Discord；通知另立具 preview、核可與 idempotency 的任務。

## 8. 後續可獨立驗收工作

1. Migration/repository foundation：工具、完整 expand migration、in-memory fixtures、ephemeral PostgreSQL contract harness。
2. Person/identity dual-read：舊 LINE/Member adapter、status guard、basic access rename、allowlist transition。
3. Qualification repository：安全 mutation、audit及 team/guest roster/statistics contract。
4. Event read model：正式 Event/Activity repository與既有 Game projection，不開 publish。
5. Event eligibility + publish snapshot：規則 preview、transaction、manual override、audit。
6. Admin identity/access/qualification UI，之後再接 attendance、crawler ownership與通知。

## 9. 仍待產品細節

- 普通使用者可看未回覆者姓名或只看人數。
- 幹部能否直接發布 Event、發送正式通知，或需第二人核可。
- 電話、醫療資訊、私人備註的欄位級可見性。
- inactive 恢復、blocked 解封的精確核可層級與保存期限。
- team_player 資格回填的權威來源與跨屆規則。
