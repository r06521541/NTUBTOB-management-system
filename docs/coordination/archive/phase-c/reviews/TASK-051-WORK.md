# TASK-051 Work 驗收

## 結論

`accepted`。repository-only production migration readiness package 已達成任務範圍；本驗收不授權 Supabase／production connection、stamp、DDL、backfill、RLS、部署或任何外部操作。

## 查驗基準

- Branch：`codex/task051-production-migration-readiness`
- Planning commit：`650d981`
- Implementation commit：`f57a29c36210080d42b6953fdae98842905977d2`
- Completion commit：`d4f259c`
- Formatting correction：`da2d7e5`
- Repository：補正後工作目錄乾淨。

## 驗收結果

- deterministic upgrade-only SQL 與 sidecar SHA-256 相符；renderer 只使用固定 localhost placeholder，不接受 DSN 或開啟 DB connection。
- static verifier 檢查 exact single-head revision chain、核准物件與 legacy ALTER allowlist，並拒絕 destructive DDL、application DML、remote／credential pattern、checksum 與 source drift。
- production runbook 分隔 Phase A schema、Phase B backfill 與 Phase C application rollout，並列出 baseline、transaction、timeout、成功／停止／recovery 與 evidence 邊界。
- RLS decision package 區分建議與未確認事實；executable artifact 未擅自加入未核准的 RLS DDL。
- 過時的 minimal two-table fixture 文件已改為 TASK-050 的 exact 10-table fake fixture。

## Work 獨立驗證

- Python 3.10.7：43/43 portal-data tests 通過。
- mid-migration failure：整筆 rollback，不留下 new tables、`members.person_id` 或錯誤 revision state。
- bounded lock：250ms test timeout 無 partial state；釋放 lock 後完整 retry 成功。
- legacy fake table counts upgrade 前後不變，新 application tables 保持空白。
- `py -3.10 -m alembic check`：`No new upgrade operations detected.`
- artifact verifier、SHA-256、`compileall`、`git diff --check` 通過。
- 首輪發現 Black 證據不實；Codex 以 `da2d7e5` 補正後，Work 獨立重跑 Black 與 Black-profile isort check 均通過。
- task-owned local PostgreSQL container 已停止，named volume 保留。

## Production blockers／Owner 決策

任何 production schema 執行前仍須另案確認：backup／PITR 與 restore authority、catalog freshness 與 baseline、runtime DB role／table owner／grants／RLS bypass、Supabase API exposure、新 tables RLS、maintenance window／lock、Phase B backfill 與 Phase C application rollout。

## 回歸風險與非阻擋事項

- local PostgreSQL 證據不能證明 production lock、network、role、RLS 或 backup 行為。
- SQL artifact 從 `0001` 升至 `0003`，假設 baseline version table／row 已依另行批准的方法建立；目前沒有 production execution tool，符合本任務安全限制。
- 未來 revision、legacy table 或 RLS 決策改變時，artifact checksum 與 readiness package 必須重新驗收。

## 下一位角色

Owner 決定 TASK-051 結案及是否授權 push／PR。即使合併，本任務也不授權 production migration。
