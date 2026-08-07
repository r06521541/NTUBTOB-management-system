# TASK-049 Work review

- 結果：`accepted`
- 執行方式：Owner 於 Supabase SQL Editor 手動執行兩份明確的 read-only SQL
- Production mutation：無
- 查驗日期：2026-08-06（Asia/Taipei）

## 已確認事實

### 安全與完整性

- catalog CSV 共 113 列，可完整解析；aggregate CSV 共 35 個 metrics。
- transaction context 回報 `transaction_read_only=on`。
- 輸出沒有 application row values、姓名、LINE ID、token、webhook identifier 或 Secret。
- production `ntubtob` 沒有 Alembic marker；`auth.schema_migrations` 與
  `realtime.schema_migrations` 是 Supabase 自身 marker。
- SQL Editor 的 `current_user` 為高權限 `postgres`，對 `ntubtob` tables 具有完整
  table privileges；本次安全性來自 read-only transaction 與查詢內容，不代表該角色
  本身是 read-only。後續 mutation 必須另行精確批准。

### 實際 legacy schema

- 10 張 application tables：`attendance_reply_types`、`ballparks`、`cancellations`、
  `discord_webhooks`、`game_attendance_replies`、`games`、`line_groups`、
  `line_notify_tokens`、`line_users`、`members`。
- 10 張 tables 都啟用 RLS，但 catalog 沒有回傳 explicit policy rows；沒有自訂
  trigger 或 `ntubtob` function。
- TASK-048 的 Person／qualification／Event foundation tables 尚不存在。
- Production 使用 PostgreSQL 15.1。主要 legacy IDs 為 `bigint` identity；TASK-048
  minimal local fixture 與部分 adapter 仍把 Member/Game ID 視為 `integer`，migration
  rehearsal 必須先校正此差異。

### Aggregate data quality

| 類別 | 結果 |
| --- | --- |
| Members | 197；空白名稱 0；normalized name collision 0 |
| LINE users | 65；已連結 56；未連結 9；其中未忽略 4、忽略 5 |
| LINE identity | duplicate subject 0；一位 Member 多 LINE account 0；orphan Member FK 0 |
| Games | 128；必要賽程欄位缺值 0；natural-key duplicate 0；已邀請 86；已取消 36 |
| Attendance replies | 1,648；NULL／orphan／invalid reply type 均為 0 |
| Cancellations table | 0 rows；orphan 0；duplicate 0 |

### Attendance duplicate 語意與待分類來源

- `game_attendance_replies` 有 106 組重複 `(game_id, member_id)`，同時有 106 組
  重複 `(game_id, user_id)`。這裡的 106 是「群組數」，不是可直接刪除的列數。
- Repository 證明舊系統在判定回覆改變時以新增 row 保存歷史：webhook 呼叫
  `GameAttendanceReply.add()`；顯示分析依 `updated_at` 反向排序後每位 Member 只採
  第一筆。但 106 組可能混合真正狀態變更、隊員連點、LINE webhook 重送、並行請求，
  或無排序查詢造成的誤判，不能宣稱全部都是有意義的歷史。
- `search_single_game_reply_of_member()` 沒有 `ORDER BY`，但 webhook 使用
  `old_replies[-1]` 判定最新回覆；SQL row order 沒有保證，屬於既存的非決定性風險。

第三份 aggregate-only classifier 已確認：

| 指標 | 結果 |
| --- | ---: |
| Duplicate game/member groups | 106 |
| Duplicate groups 內總 rows | 259 |
| 每組保留一筆後的 excess rows／transitions | 153 |
| 真正 changed-reply transitions | 144 |
| Consecutive same-reply transitions | 9 |
| Exact duplicate groups | 0 |
| Same-timestamp transitions | 0 |
| 最大單組版本數 | 21 |
| History 中更換 LINE user | 0 |
| Attendance Member 與 LINE user 配對不一致 | 0 |

144 + 9 正好等於 153 個 transitions；約 94% 是回覆狀態真的改變，約 6% 是
連續相同回覆。後者與連點／重送相容，但 aggregate 結果無法辨識確切來源。沒有 evidence
支持刪除任何 legacy row。

## Migration implications

1. 不刪除或就地加 unique constraint 到 legacy `game_attendance_replies`。
2. 新 current-state attendance table 若要回填，只能用明確且可重現的
   `ORDER BY updated_at DESC, id DESC` 為每個 game/member 選一筆；legacy history 保留。
3. 197 位 Members 可一對一建立 Person 與 `team_player` qualification；不得使用姓名
   自動合併不同 Member。
4. 56 個已連結 LINE users 可建立 linked identities；4 個未連結且未忽略者是 pending
   candidates；5 個 ignored identities 的 blocked／disabled 映射要在正式 backfill 前
   明確核准。
5. `cancellations` table 為空，但 `games.cancellation_time` 有 36 筆；相容邏輯不能假設
   cancellation 狀態來自 `cancellations` table。
6. Production 沒有 repository Alembic history。任何 baseline stamp、DDL、backfill 或
   RLS policy 都必須在 clone／local rehearsal 後另取得 Owner 精確批准。

## 尚未驗證

- 沒有查詢任何資料列值，因此未人工辨識 Member、LINE identity 或 attendance 內容。
- 沒有量測 production DDL lock time、執行 plan、backup／PITR 可用性或 database role
  ownership boundary。
- Aggregate classifier 不讀 row values，因此沒有辨識最大 21 版本群組所屬的人或比賽；
  migration 不需要此個資即可用 deterministic latest-row 規則安全回填。
- RLS enabled 但零 explicit policies 的實際 runtime access path 尚未盤點；不得據此
  推定 public API 可讀或 service role 一定受 RLS 限制。

## 結論

TASK-049 已完成且可接受。Production 資料量小、核心 FK 完整，未發現 orphan、identity
collision 或 attendance identity mismatch。現有 1,648 attendance rows 對應 1,495 個
game/member current-state groups；未來若回填 current-state table，應保留 legacy history，
並以 `updated_at DESC, id DESC` 選定每組最新 row。本結論不授權 production migration
或 legacy row deletion。
