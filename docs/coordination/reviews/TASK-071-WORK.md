# TASK-071 Work review

## 結論

`changes_requested`

驗收 commit：`e468caf2849ff00dde0359c90e22b5016ae15318`

整體 production-readiness 工作包方向正確，三份 SQL、checksum、validator、compare 與 runbook 均已建立；本機 PostgreSQL 16 完整測試亦通過 154/154。惟 Phase C post-check 尚未精確驗證新 schema 定義，因此目前不能作為 production migration 的最終成功證據。

## Blocking finding

### Phase C post-check 只計數，未驗證精確 catalog 定義

`TASK-071-phase-c-production-postcheck.sql` 目前僅檢查：

- 3 個指定欄位名稱存在；
- review tables 合計有 10 個 constraints；
- 3 個指定 index 名稱存在。

這不足以滿足 TASK-071 要求的「exact columns/tables/PK/FK/check/indexes」：

- 欄位型別、nullable、default 或 identity 錯誤仍可能通過；
- `ck_people_formal_name`、`ck_people_admin_note` 未在 post-check 被驗證；
- review tables 的 constraint 名稱與 `pg_get_constraintdef` 未驗證；
- 同名 index 即使建立在錯誤欄位或使用錯誤排序，仍可能通過。

請補上 deterministic Phase C catalog fingerprints，至少涵蓋：

1. Phase C 新增欄位的 type、nullable、default、identity；
2. 全部新增 PK/FK/check constraint 的名稱、型別、定義與 validated 狀態；
3. 全部新增 indexes 的名稱與完整 definition；
4. review tables 的 RLS/forced-RLS 與 zero-policy boundary。

validator 必須把上述 fingerprints 列為 required exact values；PostgreSQL 測試需加入負向 mutation，證明錯誤欄位定義、錯誤 constraint definition、錯誤 index definition 均會 fail closed。修改 SQL 後同步更新 checksum、runbook 與 report。

## Work 驗證

- `git diff --check 027b6b8..e468caf`：passed。
- 初始化 localhost-only PostgreSQL fixture，stamp `0001` 並 upgrade 至 head：passed。
- `python -m unittest discover -s tests/portal_data -v`：154 tests passed。
- 靜態檢查確認目前 post-check 僅使用 `phase_c_column_count`、`phase_c_constraint_count` 與 `phase_c_index_count`，未包含 Phase C exact fingerprint。

首次測試因本機 fixture 尚未建立 `ntubtob` schema 而失敗；依 repository 文件初始化隔離的 local database 後，完整 suite 通過。這是本機前置設定，不是程式失敗。

## 安全邊界

驗收期間未連線 production Supabase、未執行 production migration、未部署、未啟用 runtime flags、未發送通知，亦未修改 Secret、IAM、Scheduler 或其他雲端資源。

