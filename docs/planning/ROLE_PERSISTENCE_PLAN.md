# Web Portal 角色、權限與多類型 Event 持久化藍圖

狀態：`proposed_for_owner_decision`

本文依 TASK-047 對目前 repository 的程式、models 與測試作設計整理；不代表已批准 schema、migration、角色指派介面或 production 操作。角色權限與多類型 Event 是同一次 schema 演進藍圖，不以互不相容的逐表改造方式落地。

## 1. 已確認現況

- Production session 只保存 LINE `user_id` 與已配對的正整數 `member_id`；每次受保護請求由 `admin_security.get_current_principal()` 重新解析 principal。
- `WEB_PORTAL_ADMIN_MEMBER_IDS` 是目前唯一 production 高權限來源。有效 allowlist 命中者是 `admin`，其餘有效會員是 `member`；production 無 `officer` 來源。
- `role_policy.py` 集中定義 `member`、`officer`、`admin` 與 capability 繼承。未知 role／capability fail closed。
- Demo 可在雙重 development gate 下模擬三種角色、Event/Activity 與幹部 Event Builder；其資料只在 session，不能作為正式資料來源。
- `ntubtob.members` 目前可確認只有 `id`、`name`；`ntubtob.line_users.member_id` 負責 LINE 身分與 Member 配對，並有 `ignored`，但沒有正式角色、帳號狀態或角色稽核欄位。
- 現有 `games`、`game_attendance_replies` 是比賽與比賽出席模型；正式 Event/Activity 尚不存在。聯盟匯入與幹部手動活動必須能區分，crawler 不得覆蓋手動資料。
- Repository 沒有 migration framework；model 方法目前自行開啟 SQLAlchemy session，角色解析也尚未查 Member role。

## 2. 主體、角色與帳號狀態

角色回答「可做什麼」，狀態回答「帳號能否進入」。LINE profile、暱稱或 display name 都不能決定兩者。

| 狀態／主體 | 判定來源 | Portal 行為 |
| --- | --- | --- |
| Anonymous | session 無有效 LINE identity | 只能存取公開頁；受保護頁導向登入 |
| Pending／unmatched | LINE user 存在但沒有有效 `member_id` | 顯示等待配對；不得取得 member capability |
| Active member | Member 狀態 active、role 是 member | 隊員 capability |
| Active officer | Member 狀態 active、role 是 officer | 隊員能力加活動／球隊作業能力 |
| Active admin | Member 狀態 active、role 是 admin，或過渡 allowlist 命中 | officer 能力加成員、角色與稽核管理 |
| Disabled | Member 狀態 disabled | 所有受保護 route fail closed；保留資料供日後恢復與稽核 |
| Left | Member 狀態 left | 所有受保護 route fail closed；歷史出席／活動關聯不得刪除 |
| 未知／畸形值 | DB 或 session 不符合契約 | 一律拒絕並記安全事件 |

`ignored` 是「不處理尚未配對的 LINE user」，不是 Member 停權或離隊狀態，不應重用。

## 3. 建議整體資料模型

### 3.1 Member 單一階層角色

建議在 `ntubtob.members` 新增 nullable `portal_role`（member/officer/admin）與 `portal_status`（active/disabled/left）。第一版採單一 role，而不是 member-role assignment table：現有產品是三層階層，admin 已繼承 officer，同時具有多個角色不增加能力；request-time 只讀一列也較容易 fail closed。未來「活動 A 負責人」應是 Event 層 assignment，不是全站 role。

欄位建議用 text 加 CHECK constraint，而非 PostgreSQL enum；role → capability 仍只由 `role_policy.py` 定義。相容期 NULL role/status 分別降級 member/active，未知非 NULL 值不得降級。

### 3.2 Event／Activity 與既有 Game

建議同一演進藍圖新增下列概念；實際名稱與 DDL 在 migration 任務定稿：

- `events`：活動容器，含類型、標題、起訖時間、狀態（draft/published/cancelled）、建立者與版本時間。
- `activities`：屬於 Event 的有序行程，含類型（game/meal/transport/lodging/gathering/other）、時間、地點與可選描述。
- Game activity 以 nullable FK 連到既有 `games.id`；單場既有 Game 可由相容 backfill 取得一個 Event/Activity wrapper，不複製比賽事實。
- 手動比賽仍使用 Game domain，但要有明確 source（league/manual）及 stable external key；crawler 只能更新 league-owned 欄位，不得覆蓋 manual game。
- `event_attendance_replies` 保存整體 Event 回覆；Activity override 另表保存，只寫與整體值不同的例外。既有 game replies 在相容期繼續作為 game attendance 真實來源，直到另案雙讀完成。
- `event_manager_assignments` 可表達某 Event 的負責幹部，但建立/發布 route 仍先要求全站 `manage_events`；assignment 只限該活動作業範圍，不提升全站角色。

角色欄位、Event schema、source ownership、兩層出席與 audit 必須在一份 migration 序列與相容矩陣中驗證，避免角色已可建立活動但正式資料模型尚未安全可寫。

### 3.3 存取變更稽核

角色／狀態 mutation 上線前新增 append-only `member_access_audit`，至少含 target member、actor member、change type、old/new value、受限長度 reason、unique request ID 與 DB 產生的 timestamptz。更新與 audit 必須同 transaction。不得記 LINE user ID、session、token、cookie、完整 request body 或敏感個資。

Event 的建立、發布、取消與 source ownership 變更也需 audit，但應採 Event domain audit，而不是塞進 member access audit。

## 4. Principal 與 route 安全邊界

建議 request-time 流程：

1. 驗證 session 有非空 `user_id` 與正整數 `member_id`。
2. 依 `member_id` 讀 Member 最小 access projection，不信任 cookie 內 role/status。
3. Member 不存在、status disabled/left/未知：清除 authenticated identity 並拒絕。
4. 相容期 NULL status/role 視為 active/member；有效 DB role 交給集中 policy。
5. 過渡 allowlist 命中可提升 admin，但不得使 disabled/left 復權。
6. UI 可依 capability 隱藏入口；每個 read/mutation route 必須在讀管理資料或產生副作用前重新授權。

角色不寫入 session，讓撤銷 request-time 生效。Anonymous/pending/disabled/left 不得讀隊內資料；member 只管理自己；officer 管理 Event 與球隊作業；admin 繼承 officer 並管理 Member/role/audit。Secret、deployment、IAM、DDL 與不可逆 production data 操作永遠不因 Portal admin 自動獲得授權。

## 5. 一次到位的 migration 與相容 rollout

### Phase 0：migration 與 local integration 基礎

- 選定可版本化、可重跑、可在 CI/ephemeral PostgreSQL 驗證的 migration 工具；不可把 Supabase SQL Editor 當唯一歷史。
- 用 local ephemeral PostgreSQL（或 Supabase local）由空 schema 跑 forward migration、seed、constraint、transaction、rollback rehearsal；不得連 production。
- 產品原型繼續透過單一 in-memory repository 介面與集中 fixtures 提供 role/Event/attendance 資料，不逐表 mock ORM。這使 routes 測產品規則，正式 repository integration 則由 ephemeral DB suite 負責。

### Phase 1：expand schema，不改正式行為

- 一個 migration series 同時加入 nullable member access 欄位、access audit、Event/Activity/source/attendance 結構；先不回填、不開寫入。
- 新 FK/index/constraint 採低鎖定策略，CHECK 可先 NOT VALID 再獨立 validate；需在 production-sized 測試資料估算 lock/time。
- 舊 application revision 必須仍可讀寫既有 Member、Game 與 attendance 欄位。

### Phase 2：部署 dual-read application

- Member NULL role/status 相容；未知值 fail closed。Admin allowlist 暫時保留。
- Event read 可在 feature flag 下將既有 games 投影為單場 Event；既有 `/attendance` 與通知仍讀原 game reply，不立即切換真實來源。
- 所有 active revisions 都理解 portal_status 後，才可開啟 status mutation。

### Phase 3：受控 backfill

- 分批、可重跑地回填 member/active；allowlist admin 逐筆核對。不得由姓名或 LINE 暱稱推測 officer。
- 為既有 games 建 Event/Activity wrapper，使用 unique game reference 確保重跑不重複；league/manual source 無證據時不可猜測，列入例外報告。
- 比對筆數、orphan、時間範圍與 attendance 關聯；失敗停止，不刪 production 資料。

### Phase 4：開啟受控寫入

- 先啟用角色 mutation domain/API（CSRF、transaction、last-admin、reason、audit、idempotency），再上 UI。
- Event 依 draft → publish 開放；只有 `manage_events` 可建立/修改，發布與通知分離。既有 crawler 只負責 league source。
- Event attendance 新寫入是否同步 legacy game reply，必須由獨立 compatibility contract 決定；切換前不可讓兩邊各自成為真實來源。

### Phase 5：contract

- DB 至少兩位已驗證 active admin、break-glass 演練成功後，allowlist 才能降為緊急用途。
- Event/attendance 新讀寫與排程、LINE webhook、通知服務全部相容驗證後，才另案停止 legacy projection；drop column/table 永遠是後續獨立 migration。

## 6. Rollback

- Expand schema 保留，application 可回到相容 revision；不以 drop table/column 作緊急 rollback。
- DB officer/admin 若被舊版視為 member，是降權；allowlist 暫留以維持管理入口。
- **一旦開始寫 disabled/left，禁止回滾到不理解 portal_status 的舊 revision**，否則停權者可能恢復存取。
- Event 新寫入啟用後，rollback revision 必須理解新 Event/source ownership；否則只可切換成 read-only/停止 mutation，不能讓舊 crawler 覆蓋 manual data。
- 錯誤 role/status/Event 狀態以新的反向 mutation 修正並 append audit，不覆寫稽核歷史。

## 7. 角色指派安全

- 只有 active admin 且具 `assign_roles` 可修改；officer 不可核可、配對或指派角色。
- Mutation 必須 POST、session-bound CSRF、固定值、reason、unique request ID、actor/target request-time reload、同 transaction update + audit。
- Transaction 中重新確認 actor，並鎖定 actor/target。不可自行移除 admin；第一版由另一位 admin 操作。
- 不可移除最後一位 DB active admin。這是跨列規則，需 transaction-level singleton/advisory lock 後計數，不可只靠 CHECK。
- Bootstrap 由已核准 allowlist admin 透過一次性可稽核流程建立。Break-glass allowlist 由 Owner 控制，使用時寫不含完整名單的安全 log。
- Mutation 不自動發 LINE/Discord；未來通知另立具 preview、核可與 idempotency 的任務。

## 8. Local 與離線驗證策略

- **產品原型**：以一個 repository protocol（例如 TeamPortalRepository）包住 role、Event、Activity、reply 操作；測試注入單一 in-memory implementation 與一組明顯虛構 fixtures。不要讓每個 route 分別 mock Member/Game/Activity table。
- **純 domain tests**：capability、狀態機、source ownership、Event/Activity 時間約束、整體回覆與 override 合併、last-admin 規則。
- **Flask route tests**：只驗 request/response、CSRF、authorization 與 repository 呼叫邊界；禁止外部 HTTP/DB/通知。
- **正式 persistence integration**：ephemeral PostgreSQL/Supabase local 從 migration 建庫，測 FK/unique/check/index、transaction rollback、concurrent last-admin mutation、audit 原子性、backfill idempotency 與 repository contract。
- 同一組 repository contract tests 同時跑 in-memory 與 PostgreSQL implementation，避免 Demo 與正式行為漂移；但敏感/production資料永不作 fixture。

## 9. 建議後續可獨立驗收任務

1. Migration + repository foundation：選工具、建立完整 expand migration、repository protocol/in-memory fixtures、ephemeral PostgreSQL contract harness；仍不改 production behavior。
2. Persistent role dual-read：Member access projection、status guard、DB role + allowlist 與測試；不提供 mutation UI。
3. Event read model：正式 repository 讀取 Event/Activity，並安全投影既有 games；不開 mutation/通知。
4. Controlled backfill rehearsal：在 local ephemeral DB 驗證 member/game wrappers 的可重跑 backfill與 rollback。
5. Role mutation domain/API + audit，之後才接 admin UI。
6. Production Event draft CRUD，再分開做 publish、attendance、crawler ownership、通知整合。

## 10. 待 Owner 決策

1. 是否接受每位 Member 單一階層 role、admin 繼承 officer？（建議接受）
2. Disabled 與 left 是否都禁止登入；left 是否可恢復？（建議都禁止，disabled可恢復，left恢復需二次確認）
3. 是否至少兩位 DB active admins 後才把 allowlist 降為 break-glass？（建議是）
4. 管理員是否一律不得自行降權？（建議是）
5. 普通隊員可看未回覆者姓名或只看人數？
6. 幹部能否直接發正式通知，或需另一人核可？
7. 電話、醫療資訊、私人備註各允許哪些角色查看？
8. Event 發布是否需要第二位幹部核可？發布與發送通知建議保持兩個操作。
