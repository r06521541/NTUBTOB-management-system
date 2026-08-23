# Mobile API 缺口清單

本文件只記錄 Flutter 已驗證需要、但目前 `apps/mobile_api/openapi.json` 尚未提供的跨系統契約。它不是實作授權；每項仍須另開 L2／L3 task，完成 authorization、contract、相容性與必要 migration review。

| 缺口 | 目前影響 | 建議契約方向 | 預估邊界 |
| --- | --- | --- | --- |
| 賽事列表中的本人回覆摘要 | 會員行動首頁需逐場讀取 attendance，雖已限制併發與數量，仍不是理想 dashboard projection | 在已授權的 `Game` projection 提供 `own_reply` 或 bounded batch read；維持 principal-scoped authorization | API/shared boundary；預期不需 schema |
| 尚未回覆者的通知 audience/action | App 可顯示尚未回覆名單，但沒有 server-owned「通知這批人」contract | 由 server 重新解析當下未回覆 audience，採 idempotency、rate limit、結果摘要與 audit；client 不提交任意 recipient IDs | L3 notification/security；audit 能力可能需要 schema |
| 行動端賽事狀態完整度 | 某些 Web 決策可能依賴取消狀態或其他既有賽事 eligibility，而 Mobile `Game` projection 未必完整暴露 | 只補決策真正需要且可授權的 canonical fields；先核對既有資料來源，避免複製 Web view model | API/shared boundary；是否需 schema 取決於既有資料 |

## 使用規則

- Flutter 孵化功能可先用已授權、已載入資料做 local prototype，但必須標示未知／不可用，不能猜測缺失資料。
- Lineup Lab 依 Owner 決策永久維持 session-local；不規劃官方提交、跨裝置同步、版本、併發或 audit API。任何未來方向變更都需新的 Owner 決策。
- 教練角色不受資格限制，任何已授權報告中的出席候選人皆可在 session-local Lineup 中選為教練；API 不需提供 `member_id` 或 coach eligibility。
- 任何新增 recipient、正式寫入、跨裝置同步、audit、schema 或 production provider 行為，都退出孵化豁免。
- 缺口完成後，應同步 OpenAPI、consumer tests、Flutter integration model 與本清單狀態；不要只改其中一端。

## 已完成

- TASK-156：Attendance Report 已提供 nullable `member_number`，沒有暴露 `member_id`；Flutter Lineup 已顯示背號並允許任何出席候選人擔任 session-local 教練。PR #179 的 PostgreSQL 15/16、Mobile API 與 Flutter hosted gates 均通過，未修改 schema。
