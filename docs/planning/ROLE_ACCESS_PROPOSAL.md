# Web Portal 角色與權限提案

狀態：`approved_direction`（TASK-041 第一階段方向已核准）
範圍：產品規則與未來 RBAC 邊界；Owner 已核准先建立不需 schema 的集中式權限基礎，但本文仍不代表已批准 schema、migration、角色指派 UI 或正式環境變更。

## 目標

Web Portal 對使用者呈現三種容易理解的角色：普通隊員、幹部、系統管理者。後端未來宜以細分 capability 驗證權限，避免把所有高權限綁成一個難以拆分的角色。

## 權限提案

| 能力 | 普通隊員 | 幹部 | 系統管理者 |
| --- | --- | --- | --- |
| 查看 Dashboard、公告、賽程與活動 | 是 | 是 | 是 |
| 回覆自己的出席、交通、抵達時間與裝備認領 | 是 | 是 | 是 |
| 管理自己的通知偏好與基本資料 | 是 | 是 | 是 |
| 查看隊內名單與活動參與資訊 | 限一般隊內資訊 | 是 | 是 |
| 建立／編輯／發布／取消活動 | 否 | 是 | 是（暫定繼承） |
| 新增友誼賽、OB 賽、旅遊及複合活動 | 否 | 是 | 是（暫定繼承） |
| 查看完整出席與未回覆名單 | 待決定 | 是 | 是 |
| 管理比賽日名單、分工、裝備與共乘 | 否 | 是 | 是（暫定繼承） |
| 準備通知、預覽並送出 | 否 | 是，但送出規則待決定 | 是 |
| 核可帳號、成員配對、停用／恢復成員 | 否 | 建議否 | 是 |
| 指派角色、處理登入綁定與查看稽核紀錄 | 否 | 否 | 是 |
| Secret、部署、IAM、正式資料不可逆操作 | 否 | 否 | 不由網站角色自動授權 |

## 資料可見性

資料至少分三層：公開球隊資訊、登入後隊內資訊、管理資訊。電話、醫療資訊、私人備註等敏感資料不得僅因「隊內可見」而全部開放，應另定欄位級規則與稽核需求。

## 建議 capability

- `reply_own_attendance`
- `manage_events`
- `view_team_attendance`
- `manage_game_day`
- `prepare_notifications`
- `send_notifications`
- `manage_members`
- `approve_accounts`
- `assign_roles`
- `view_audit_log`

第一版 RBAC MVP 建議只落實三條清楚邊界：所有已核可成員可管理自己的出席；幹部以上可管理活動；只有系統管理者可配對帳號與指派角色。

## 待 Owner 決策

1. 普通隊員可看未回覆者姓名，還是只看人數？
2. 幹部能直接發送正式通知，還是必須二次確認或另一人核可？
3. 系統管理者是否在 UI 上自動擁有全部幹部能力？建議第一版是，但後端 capability 保留拆分可能。
4. 幹部能否核可新帳號或進行 Member 配對？建議第一版不行。
5. 電話、醫療資訊、私人備註各自允許哪些角色查看？

## 實作前置條件

在進入正式實作前，需先確認現有 Member model、登入 session 與管理 allowlist 的相容演進方案，再提出 migration、回填、舊版相容與 rollback。本文不授權修改 schema。

TASK-047 的 repository 盤點與角色＋多類型 Event 一體化持久化藍圖另見
[`ROLE_PERSISTENCE_PLAN.md`](ROLE_PERSISTENCE_PLAN.md)。其中的單一階層 role、分離帳號
status、request-time DB 解析與 admin allowlist 過渡仍待 Owner 決策，不代表 migration 已獲批准。
