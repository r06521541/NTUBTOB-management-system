# TASK-052 Work 驗收

## 結論

`accepted`。Supabase access-boundary inventory query、去識別輸出 contract、static verifier／validator 與 Owner 操作指引符合 repository-only 準備範圍；不授權執行 production query 或任何 schema／RLS／role／backup 變更。

## 查驗基準

- Branch：`codex/task052-supabase-access-inventory`
- Implementation commit：`557b6efddb2a6a7863685eb5dd75b8039c8bcd4e`
- Completion commit：`b1d59f9`
- Repository：驗收開始與完成時乾淨。

## 驗收結果

- SQL 是單一 `BEGIN TRANSACTION READ ONLY`，使用 transaction-local timeout並以 `ROLLBACK` 結束。
- Query sources 限於固定 catalog allowlist，沒有 application row read、DDL／DML、role change、network／file helper。
- 輸出固定為 33 metrics／6 columns；role、owner、policy identity 已降為 boolean、關係或 counts。
- TASK-049 的 10-table、53-column、16 PK/FK evidence 已轉為 comparison-only fingerprints。
- CSV validator 拒絕欄位／順序／cardinality drift、未知／重複 metric、多 value及敏感內容。
- Owner 指引分開 SQL Editor 與 Dashboard-only backup/PITR、API exposure、connection path及 maintenance window。

## Work 獨立驗證

- Python 3.10：TASK-052 專屬 11/11 tests 通過。
- artifact verifier、compile、Black、Black-profile isort、`git diff --check` 通過。
- Work 額外在 localhost PostgreSQL 16.4 fake baseline 實際執行 reviewed SQL：parser 接受並輸出 exactly 33 rows；transaction rollback。
- clean baseline：legacy table count 10、new portal table count 0、table／column fingerprint match。
- local constraint fingerprint 預期為 false：fake fixture 使用 PostgreSQL 自動 constraint names，production constant 依 TASK-049 保存的 16 個正式 constraint names／definitions 推導；不據此推論 production drift。
- task-owned container 已停止，named volume 保留。

## Blocking／後續人工證據

- Query 尚未在 Supabase 執行；production output、catalog freshness、role／owner／grant／RLS 均未知。
- Backup/PITR、restore authority、API exposure、connection path、maintenance window與 timeout acceptance 須由 Owner 在 Dashboard 查驗。
- Production migration 仍 blocked；TASK-051 Phase A 未獲授權。

## 回歸風險與非阻擋事項

- SQL Editor CSV boolean 呈現若不是 contract 的 `true/false`，應停止檢查，不得手改結果繞過 validator。
- Fingerprints 故意包含 constraint names 與 catalog-rendered definitions；drift 應調查，不可直接更新常數。
- Raw export 必須留在 repository 外，只保存核准的最小去識別摘要。

## 下一位角色

Owner 決定結案與 push／PR；若要取得 production evidence，須另行批准本人在 Supabase SQL Editor 執行 reviewed query，Codex／Work 不代為登入或執行。
