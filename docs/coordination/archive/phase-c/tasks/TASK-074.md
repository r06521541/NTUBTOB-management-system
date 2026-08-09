# TASK-074：修正 Phase C PostgreSQL 15 readiness gate

## 任務目標

修正 TASK-071 readiness package 將 production 最低版本誤設為 PostgreSQL 16 的問題。以 production 已確認的 PostgreSQL 15 建立完整、可重現的 migration 與 evidence 驗證，同時保留 PostgreSQL 16 相容性；修正後重新鎖定三份 SQL checksum，供 TASK-073 重新取得 fresh inventory。

## 背景與已確認事實

- TASK-073 第一份 fresh inventory 於 2026-08-08 09:39 Asia/Taipei 匯出，strict validator 唯一 required failure 為 `server_major_at_least_16 = false`。
- Production Supabase 回報 PostgreSQL major version 15。
- 其他 required inventory gates 未被 strict validator 回報失敗；`session_bypassrls = true` 是既有明示 risk，不是本次 required failure。
- 因 required gate 失敗，未執行 migration、DDL、DML、部署或 runtime flag 變更；該 CSV 不得提交 repository，且已不再視為 fresh evidence。
- 現有 Compose 與 GitHub Actions 只測 `postgres:16.4-alpine`，validator 亦硬編碼 `server_major_at_least_16`。

## 工作範圍

1. 先建立能重現 PostgreSQL 15 被錯誤拒絕的測試。
2. 靜態檢查 Alembic `0003 -> 0004` source、rendered SQL、inventory與post-check SQL是否含 PostgreSQL 16-only 語法或 catalog 假設。
3. 將 readiness contract 改為明確接受 PostgreSQL major 15與16，拒絕14以下及無法解析／未知版本；metric名稱與validator schema須一致且fail closed。
4. 在localhost-only PostgreSQL 15執行完整legacy fixture、0001 stamp、upgrade至0004、inventory、migration、post-check、compare及全部failure rehearsals。
5. 保留現有PostgreSQL 16驗證；CI必須對15與16執行相同核心portal-data suite，不得只將image從16改成15。
6. 若 PostgreSQL 15與16的`information_schema`／`pg_catalog`文字輸出造成fingerprint差異，必須採語意仍精確的canonical normalization，或明確且受測試保護的version-specific fingerprints；不得刪除fingerprint或退回name/count-only驗證。
7. 更新inventory／post-check SQL、strict validator、checksums、runbook、TASK-073引用的exact checksums、測試及必要CI／Compose文件。
8. 撰寫Codex report並交回Work驗收。

## 明確非目標

- 不執行或連線production Supabase inventory、migration、post-check或任何SQL。
- 不升級Supabase PostgreSQL版本。
- 不部署Web Portal、LINE webhook或其他服務，不開啟runtime／identity-maintenance flags。
- 不修改Phase C產品規則、schema設計、migration語意或application行為。
- 不操作Secret、IAM、Scheduler、RLS policies、grants或其他cloud resources。
- 不提交production CSV、connection string、credential、個資或application rows。

## 驗收條件

- PostgreSQL 15與16均通過相同的clean migration、post-check、compare及failure rehearsal contract。
- PostgreSQL 14以下、未知／畸形版本 evidence會fail closed。
- Exact column／constraint／index fingerprints、RLS／forced-RLS／zero-policy與Phase B invariants沒有弱化。
- 三份SQL artifact的checksum sidecars與verifiers一致，TASK-073引用同步更新。
- Python 3.10 hosted CI明確顯示PostgreSQL 15與16 jobs成功。
- `python -m tools.portal_data_phase_c_migration verify`、evidence verify、readiness verify、compileall、完整portal-data tests及`git diff --check`通過。

## 必要測試

```powershell
python -m tools.portal_data_phase_c_migration verify
python -m tools.portal_data_phase_c_evidence verify
python -m tools.portal_data_phase_c_readiness verify
python -m compileall -q migrations tools tests/portal_data
python -m unittest discover -s tests/portal_data -v
git diff --check
git status --short
```

Codex須記錄PostgreSQL 15與16各自的實際image版本、測試數量與結果。Windows沒有全域`python`時可使用workspace Python，但不得修改Makefile或降低測試範圍。

## 相關檔案

- `.github/workflows/python-tests.yml`
- `docker-compose.portal-data.yml`
- `docs/operations/sql/TASK-071-phase-c-production-inventory.sql`
- `docs/operations/sql/TASK-071-phase-c-production-postcheck.sql`
- 兩份SQL的`.sha256` sidecars
- `docs/operations/data/PORTAL_DATA_PHASE_C_PRODUCTION_READINESS.md`
- `docs/coordination/tasks/TASK-073.md`
- `tools/portal_data_phase_c_readiness.py`
- `tests/portal_data/test_phase_c_readiness.py`

## 已知風險

- PostgreSQL版本間可能有catalog definition文字差異；修正不得以弱化驗收契約處理。
- CI matrix會增加測試時間，但這是production runtime compatibility的必要證據。
- TASK-074合併後，TASK-073原有commit及三份checksum全部失效；必須重新鎖定並重新取得fresh inventory。

## Owner決策與授權

Owner已同意建立此修正任務。一般Git／PR工作包依`COLLABORATION.md`長期授權執行；不包含production database、migration、deployment或cloud mutation。

## Base commit

`4e0c30f1277058b9d27a4941454f6e8dcc2b978d`
