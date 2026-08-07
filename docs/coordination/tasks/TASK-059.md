# TASK-059：Phase A 即時 production read-only baseline

## 任務目標

在已確認可備份與還原後，於預定 Phase A migration window 開始時重新取得 production catalog、migration
marker、RLS與 generic access boundary 的唯讀快照。結果通過後，Work 才能提出 exact migration execution
package；本任務不執行 DDL、DML、baseline stamp或 migration。

## 已批准輸入

- SQL：`docs/operations/sql/TASK-052-supabase-readonly-access-boundary.sql`
- SHA-256：`6b5da04cb357e2f261c0d37a7cf68ece3a534bc94a9fb2afb3def26e0d154260`
- SQL contract：單一 `BEGIN TRANSACTION READ ONLY`，transaction-local timeout，固定 catalog queries，單一
  six-column result，最後 `ROLLBACK`。
- Owner 已於 2026-08-07 表示目前是最佳執行時間並批准開始唯讀 baseline。

## Owner 唯一需要親手執行的動作

1. 在 Supabase SQL Editor 開啟新 query。
2. 從 repository 複製上述 SQL 全文，不修改任何字元；確認第一句是 `BEGIN TRANSACTION READ ONLY`，最後一句
   是 `ROLLBACK`。
3. 執行一次。遇到 warning、permission error、timeout、額外 result set或 unexpected prompt立即停止，不修改
   SQL重試。
4. 只匯出結果表為 CSV；固定 header 必須是：

```csv
section,metric,status,boolean_value,integer_value,text_value
```

5. 將 CSV 存在 repository 外並交給 Work。不要提供 screenshot、project ref、URL、DSN、role/account name、
   password、token或 SQL Editor周邊畫面。

## 時效性

- Catalog fingerprint、Alembic marker、RLS與 grants在沒有 DDL／policy／role change時通常穩定；一般出席回覆
  不會改變本 SQL的結果。
- 本次 baseline只供目前 migration window使用。若結果取得後發生 deployment、schema/RLS/grant變更、手動
  SQL維護、production incident，或未能在同一工作時段完成 migration preflight，baseline失效並須重跑。
- Work review通過不自動授權 migration；exact SQL checksum、transaction、timeout、stop/recovery與 post-check
  必須另行提交 Owner批准。

## 驗收條件

- CSV為固定 33 metrics／six columns，offline validator通過。
- `transaction_read_only`、`ntubtob_exists`與三個 legacy fingerprints為 true。
- Legacy table count與RLS-enabled count均為10。
- `alembic_version_exists=false`，new portal table count為0。
- Server major、owner/privilege/RLS/policy generic evidence與已接受 TASK-052 boundary一致，沒有未解釋 drift。
- Raw CSV保留於 repository外；repository只記錄去識別化 pass/fail summary。

## 明確未授權

- 不授權 migration、DDL/DML、baseline stamp、backfill、RLS/grant/role change或任意修改 SQL。
- 不授權 Work/Codex讀 credential、連 Supabase、執行 production query或操作 Dashboard。
- 不授權 deployment、notifications、Secret/IAM/Scheduler/cloud change。
- 不授權把 raw CSV、connection/session identity或敏感 metadata提交 Git。

## Stop conditions

- SQL hash／內容漂移、非 read-only transaction、缺少 rollback、輸出 contract不符。
- 任一 required fingerprint false、unexpected migration marker/new table、schema count drift。
- 執行後發生任何 schema/access/deployment維護或時間窗中斷。

## Base commit

`8f41dbcdb1d1dbcf271b02e08d3cefb250466e48`
