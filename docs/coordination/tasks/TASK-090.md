# TASK-090：Phase D capability and smoke planning

task_type: planning
delivery_group: phase-d-capability-and-smoke
requires_independent_pr: false
status: planning
owner: work
codex: codex

## 目的

在 TASK-089 已整合至 `main` 後，先收斂 officer／basic capability 與非 production browser smoke 的產品契約，
再決定後續 implementation delivery unit。此 TASK 不直接修改程式或 production。

## 已確認的 capability 方向

| 能力／操作 | Basic | Officer | Admin |
| --- | --- | --- | --- |
| 查看 Person 列表 | 是（低敏資料） | 是 | 是 |
| 編輯本人暱稱 | 是 | 是 | 是 |
| 編輯他人基本資料 | 否 | 是 | 是 |
| 處理 pending identity | 否 | 是 | 是 |
| 新增 Member | 否 | 是 | 是 |
| 管理 qualification | 否 | 是 | 是 |
| 變更 access/status、角色與高風險安全操作 | 否 | 待另定 | 是 |
| 準備通知 | 否 | 是 | 是 |
| 發送正式通知 | 待定 | 待定 | 待定 |

## 產品與安全邊界

- Basic 查看 Person 僅提供低敏欄位；電話、醫療資訊、私人備註、完整 provider subject 與 Secret 永不因列表權限開放。
- 暱稱只能由本人修改；Officer 可修改他人的基本資料，但不得藉此修改暱稱。
- Officer 可進入 `/manage/...` 管理頁；URL 不綁定角色名稱，實際存取由 capability policy 決定。
- last-admin、self-lockout、blocked recovery、CSRF、request-time reload、audit atomicity 與 fail-closed 不變。
- 正式通知發送權限與二次核可流程暫不決定；本 TASK 只規劃 prepare／send 邊界。

## Smoke planning

- 一般瀏覽器與 LINE in-app browser 各建立登入、callback state／nonce、cookie、return path、權限拒絕與 CSRF 情境。
- 驗收使用非 production 環境、測試帳號與遮罩證據；不使用正式 Secret、正式資料或真實通知。
- Production smoke、allowlist cutover、deployment、DB mutation、IAM、Scheduler 與 Secret 操作均需另案明確批准。

## 交付物

- capability matrix 與 route／operation mapping。
- officer 與 admin 的高風險操作界線及待決事項。
- browser／LINE in-app smoke runbook、證據格式與停止條件。
- 下一個 implementation TASK 的範圍、非目標、驗收條件與最小充分測試。

## 下一步決策

- Officer 是否可變更 Person access/status、角色與 blocked recovery。
- Basic Person list 的可見欄位與是否顯示 Member／qualification 摘要。
- 正式通知是否需要 admin、二次確認或雙人核可。
