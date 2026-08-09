# TASK-088 identity/admin manual smoke

本文件是人工驗收準備，不代表已連線 production、完成正式 mutation 或完成部署。

## 執行前置

- 使用 Work/Owner 指定的非 production 環境與測試帳號；不得使用正式資料、Secret 或真實通知。
- 確認 `PORTAL_DATA_PHASE_C_ENABLED`、`PORTAL_DATA_IDENTITY_MAINTENANCE_ENABLED` 與必要測試資料已由環境管理者提供。
- 準備一個一般瀏覽器與 LINE in-app browser；兩者都使用新的登入 transaction。
- 每個 mutation 準備唯一 `request_id`、至少三字元 reason，並保留 CSRF failure 與 authorization failure 的 response。

## 瀏覽器與 LINE in-app browser 情境

| 情境 | 操作 | 成功證據 | 失敗證據／風險 |
| --- | --- | --- | --- |
| 未登入管理入口 | 開啟 `/match-member` | 導向登入選擇頁，未查詢或顯示管理資料 | 若直接顯示管理頁，停止驗收 |
| 一般瀏覽器登入 | 從管理入口完成 LINE Login | callback 僅接受同一 session 的 state/nonce，回到管理入口 | state/nonce 不一致應為 400；不得重試正式 callback |
| LINE in-app browser | 以 LINE 內建瀏覽器開啟管理入口並完成登入 | session cookie 與安全 return path 正常，管理入口可載入 | 若 cookie 或 callback 失效，記錄 UA、時間與 bounded response；不得放寬 CSRF/SameSite |
| pending identity match | 選既有 Member，填 reason 後送出 | identity 變為 linked，Member/Person 對應正確，產生一筆 audit | display name 不得自動推測身分或資格 |
| pending identity non-member | 填明確 display name 與資格後送出 | 建立 non-member Person，資格與 identity 同 transaction | 缺 reason、CSRF、request-id 或資格資料不完整應拒絕 |
| ignore/reject | 執行暫時忽略與拒絕 | 狀態與 append-only audit 正確；相同 request-id 可安全重試或明確回報 drift | 未配對、disabled/inactive/blocked 應 fail closed |
| admin safety | 嘗試停用自己、移除最後 active admin | mutation 被拒絕且無 audit/data partial write | 若權限或 audit 狀態部分提交，停止驗收 |

## 證據格式

每個情境記錄：`environment`、`browser`、`timestamp`、`route`、`actor class`、`request_id`（可遮罩）、HTTP status、畫面或 bounded response 截圖、audit/result 摘要，以及未驗證風險。不得記錄 token、cookie、Secret、完整 provider subject 或正式資料內容。

本文件完成不等於 production smoke；production 執行仍需 Owner 當次明確批准。
