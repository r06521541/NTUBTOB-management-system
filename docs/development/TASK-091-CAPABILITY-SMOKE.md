# TASK-091 capability smoke 準備

本文件只描述 local／staging-like 測試資料的瀏覽器與 LINE in-app browser smoke，禁止連接 production、正式資料或發送真實通知。

## 測試矩陣

以明確的 demo principal 或隔離測試帳號驗證：

| 角色 | 應可用 | 應拒絕 |
| --- | --- | --- |
| Basic | `/manage/people` 低敏列表、自己的暱稱 | 他人編輯、pending、qualification/access 管理、通知 confirm/send |
| Officer | Person 基本資料、pending identity、新增 Member、qualification/access/status、通知 prepare/confirm | 自我升權、指派/移除 admin、移除最後 active admin、blocked recovery、通知 send |
| Admin | Officer 能力與角色／通知管理 | 仍須通過 CSRF、reason、request-id 與 audit/idempotency 檢查 |

## 瀏覽器與 LINE in-app browser 步驟

1. 使用隔離資料登入，記錄 URL、角色、時間、HTTP status 與畫面結果；確認 `/manage/people` 可搜尋／分頁，詳情頁不顯示 provider subject、電話、醫療或 admin note。
2. 以 Basic、Officer、Admin 各執行一次允許與拒絕操作；拒絕請記錄 403／redirect，不重試到 production。
3. 以 LINE in-app browser 開啟相同 local／staging-like URL，記錄 viewport、登入方式、CSRF 結果、返回導覽與 screenshot 路徑；不可使用真實 LINE 使用者或發送通知。
4. 通知只驗證 prepare → confirm → send 的請求契約與 preview；send 步驟使用 stub／dry-run，證據須標示「未發送」。

## 證據格式

`environment=local|isolated-staging-like; role=basic|officer|admin; route=...; action=...; expected=...; observed_status=...; notification_sent=false; timestamp=...; screenshot=...`
