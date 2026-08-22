# Mobile API 缺口清單

本文件只記錄 Flutter 已驗證需要、但目前 `apps/mobile_api/openapi.json` 尚未提供的跨系統契約。它不是實作授權；每項仍須另開 L2／L3 task，完成 authorization、contract、相容性與必要 migration review。

| 缺口 | 目前影響 | 建議契約方向 | 預估邊界 |
| --- | --- | --- | --- |
| 賽事列表中的本人回覆摘要 | 會員行動首頁需逐場讀取 attendance，雖已限制併發與數量，仍不是理想 dashboard projection | 在已授權的 `Game` projection 提供 `own_reply` 或 bounded batch read；維持 principal-scoped authorization | API/shared boundary；預期不需 schema |
| 出席報告的 Lineup 候選資料 | Mobile report 只有 `person_id`、`display_name`、`reply`，無法判定教練資格，也不能顯示 Web 的背號 | 僅對既有可見賽事與 Officer/Admin 提供穩定 `member_id`／coach eligibility、`member_number`；不得由姓名或 capability 猜測 | API/privacy/authorization；若重用既有 Member 欄位，預期不需 schema |
| 尚未回覆者的通知 audience/action | App 可顯示尚未回覆名單，但沒有 server-owned「通知這批人」contract | 由 server 重新解析當下未回覆 audience，採 idempotency、rate limit、結果摘要與 audit；client 不提交任意 recipient IDs | L3 notification/security；audit 能力可能需要 schema |
| 官方 Lineup 草稿／提交 | 目前 Lineup Lab 只在 session 記憶體內，不能跨裝置、協作或成為正式名單 | 版本化 read/save/submit contract，server 驗證候選資格、守位、棒次、DH 規則、寫入權限與 idempotency | L3 API/data；大概率需要 schema/migration |
| Lineup 併發與稽核 | 沒有 server state，因此無法處理兩位幹部同時編輯、變更歷史或回復 | 與官方 Lineup contract 一起提供 revision/ETag、conflict response、actor/time audit 與 rollback policy | L3 schema/security |
| 行動端賽事狀態完整度 | 某些 Web 決策可能依賴取消狀態或其他既有賽事 eligibility，而 Mobile `Game` projection 未必完整暴露 | 只補決策真正需要且可授權的 canonical fields；先核對既有資料來源，避免複製 Web view model | API/shared boundary；是否需 schema 取決於既有資料 |

## 使用規則

- Flutter 孵化功能可先用已授權、已載入資料做 local prototype，但必須標示未知／不可用，不能猜測缺失資料。
- 任何新增 recipient、正式寫入、跨裝置同步、audit、schema 或 production provider 行為，都退出孵化豁免。
- 缺口完成後，應同步 OpenAPI、consumer tests、Flutter integration model 與本清單狀態；不要只改其中一端。
