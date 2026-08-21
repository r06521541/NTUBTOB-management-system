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
| 變更 access/status | 否 | 是（受限） | 是 |
| 指派 admin、移除最後 admin、blocked recovery | 否 | 否／需 admin 或二次確認 | 是 |
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

## 已確認的新增決策

- Officer 可變更 Person 的 access/status，但必須禁止自我升權、自我解鎖、自我恢復，以及任何 admin 指派或最後
  active admin 移除；每次操作需 reason、request ID、audit 與 transaction-level guard。
- Officer 不直接執行 blocked recovery；需要 admin 或明確二次確認，避免一般幹部成為高風險復原者。
- Basic 的 Person 列表至少顯示低敏的 access/status 與「作為球員」相關資格摘要；目前缺少的欄位另列後續補強，不為
  此任務臨時擴大 schema 或洩漏電話、醫療、私人備註等資料。
- 比賽與未來 Event 的正式通知發送採二次確認；prepare 與 send 分離，第二次確認需可稽核且具 idempotency。

## 尚待定義

- Officer 的 access/status 可變更集合與每個狀態的精確 transition matrix。
- Basic Person list 的 access/status 與球員資格摘要欄位清單、遮罩規則與缺漏欄位補強 task。
- 正式通知二次確認者的角色條件、有效期限、重試與撤回語意。
