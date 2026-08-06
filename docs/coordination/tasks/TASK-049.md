# TASK-049：Supabase production schema 唯讀盤點

## 目標

在不修改 Supabase production、不讀取個資與 Secret 的前提下，取得
`ntubtob` schema 的實際資料表、欄位、constraint、index、trigger、RLS、
目前查詢角色權限及估算資料量，作為後續 production migration 設計的事實基礎。

## 執行方式

採 Owner 核准的路線 A：Work 準備唯讀 SQL，Owner 在 Supabase SQL Editor
手動執行，再將單一結果表匯出交回 Work 分析。

第一階段 catalog SQL 位於
`docs/operations/sql/TASK-049-supabase-readonly-inventory.sql`。第一階段確認實際
legacy schema 後，第二階段 aggregate SQL 位於
`docs/operations/sql/TASK-049-supabase-readonly-data-quality.sql`。
若 attendance duplicate groups 非零，第三階段分類 SQL 位於
`docs/operations/sql/TASK-049-supabase-readonly-attendance-history.sql`；它只比較相鄰
版本並回傳 aggregate counts，不輸出 identity、game、reply 或 timestamp values。

## 已確認安全邊界

- SQL 以 `BEGIN TRANSACTION READ ONLY` 開始並以 `ROLLBACK` 結束。
- 僅使用 `SET LOCAL` 與 `SELECT`，不包含 DDL、DML、GRANT、migration、stamp
  或 backfill。
- 查詢只讀 PostgreSQL catalog、`information_schema` 與統計資訊。
- 不選取 application table 的實際資料列；輸出不應包含姓名、LINE ID、
  email、token 或其他使用者資料。
- 資料量來自 PostgreSQL catalog 的估算值，不會為了精確計數掃描 production
  application tables。
- 不讀取 `envs/**/.env.yaml`，不要求或記錄 Supabase connection string。

## 範圍

- connection context：database、current role、PostgreSQL version、read-only 狀態。
- `ntubtob` schema owner。
- tables、partitioned tables、views、materialized views 與估算 rows/size。
- columns、data types、nullable、defaults、identity/generated 屬性。
- primary key、unique、foreign key、check、exclude constraints。
- indexes、非 internal triggers、schema functions 的介面與安全屬性。
- RLS flags 與 policies。
- current role 對各 table 的 SELECT/寫入/DDL-adjacent privileges 摘要。
- repository 常見 migration marker table 是否存在。

## 非目標

- 不取得或顯示任何 application row value。
- 第一階段 catalog query 不執行精確 `COUNT(*)`。第二階段只針對已確認且規模小的
  legacy tables 執行低負載 aggregate counts；不回傳任何資料列值。
- 不建立 read-only database role，不操作 database password 或 Secret。
- 不執行 Alembic `stamp`、migration、DDL、backfill、lock 或 production transaction。
- 不部署、不修改 Web Portal 或其他服務。

## Owner 執行步驟

1. 在 Supabase Dashboard 開啟 production project 的 SQL Editor。
2. 建立新 query，貼上完整 SQL。
3. 執行前確認非註解 statement 只有 `BEGIN TRANSACTION READ ONLY`、
   `SET LOCAL`、`SELECT`、`ROLLBACK`。
4. 執行一次；結果應為 `section`、`object_name`、`details` 三欄。
5. 將結果匯出 CSV。若要貼回對話，可先移除 `connection_context` 列中的
   `database` 與 `current_user`；不可附上 browser URL、connection string 或密碼。
6. 若出現錯誤，停止，不要自行改寫 SQL；只回報不含憑證的錯誤訊息。

第一階段結果經 Work 確認後，第二階段使用相同步驟執行 aggregate SQL；輸出應為
`section`、`metric`、`value` 三欄。只需提供匯出的 CSV，不需提供 SQL Editor URL。

## 驗收條件

- SQL 可在隔離 PostgreSQL fixture 上以 read-only transaction 執行。
- 結果為單一表格並涵蓋上述 catalog 類別。
- SQL 靜態檢查沒有 production mutation statement。
- `git diff --check` 通過。
- 實際 Supabase 結果由 Work 查驗後，才能規劃下一個 migration rehearsal task。

## 停止條件

- SQL Editor 顯示 transaction 不是 read-only。
- 查詢要求輸入或輸出 application row values、Secret 或連線字串。
- 查詢遇到 permission error、timeout 或 lock wait。
- 發現 production 已有未知 migration marker、同名新 foundation tables，或
  current role 擁有超出預期的寫入能力；先記錄事實，不做任何修正。

## Base commit

`316332df39591f47f542bb5e69be9caeb7dbd925`
