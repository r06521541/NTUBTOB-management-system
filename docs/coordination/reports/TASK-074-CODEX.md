# TASK-074 Codex report

## 任務狀態

- 狀態：`ready_for_review`
- Branch：`codex/task-074-postgres15-phase-c-readiness`
- Base commit：`4e0c30f1277058b9d27a4941454f6e8dcc2b978d`
- 實作 commit：`29854a5bcda321d16a046f44611a813b0615f26a`
- Production、Supabase、Secret、部署、runtime flags、通知及其他 cloud resources：均未存取或變更

## 實際修改

- 將 inventory／post-check 的 required metric 改為 `server_major_supported`，SQL 只接受
  PostgreSQL major 15或16；14以下及未審查的新major會輸出`false`，缺值、畸形或其他非`true`
  evidence由strict validator fail closed。
- Repository verifier額外鎖定exact SQL version expression；即使同步修改sidecar checksum，也不能把
  gate放寬為`>= 15`。
- 保留19個Phase C columns、15個constraints、3個indexes的exact fingerprints，以及既有RLS、
  forced-RLS、zero-policy、Phase B與audit relationship gates。PostgreSQL 15.8及16.4均使用同一組
  fingerprints通過，未採name/count-only或version-specific弱化。
- Compose保留PostgreSQL 16.4預設，新增`PORTAL_DATA_POSTGRES_IMAGE`供明確切換15.8；GitHub Actions
  改為15.8／16.4 matrix，兩個Python 3.10 jobs執行相同完整suite。
- 重新鎖定inventory與post-check sidecar；migration artifact未變，checksum仍為
  `67ea4490a1e3459221f440ae280e95f3be5a868ad2c37c78ae3519073e7d1f91`。
- Runbook及TASK-073同步新checksums，並明示TASK-074 squash merge後仍須填入exact merged commit及
  重新取得30分鐘fresh inventory；先前TASK-073 CSV已失效。

## 修改檔案

- `.github/workflows/python-tests.yml`
- `docker-compose.portal-data.yml`
- `tools/portal_data_phase_c_readiness.py`
- `tests/portal_data/test_phase_c_readiness.py`
- `docs/operations/sql/TASK-071-phase-c-production-inventory.sql`
- `docs/operations/sql/TASK-071-phase-c-production-inventory.sql.sha256`
- `docs/operations/sql/TASK-071-phase-c-production-postcheck.sql`
- `docs/operations/sql/TASK-071-phase-c-production-postcheck.sql.sha256`
- `docs/operations/data/PORTAL_DATA_PHASE_C_PRODUCTION_READINESS.md`
- `docs/coordination/tasks/TASK-073.md`

## 驗證結果

- 回歸測試先在舊實作失敗：缺少`server_major_supported` schema metric；修正後通過。
- `postgres:15.8-alpine`（實際 PostgreSQL 15.8）：完整portal-data suite 157/157 passed。
- `postgres:16.4-alpine`（實際 PostgreSQL 16.4）：完整portal-data suite 157/157 passed。
- 兩個版本皆從clean task-owned volume建立legacy fixture、upgrade至0004，並執行clean
  inventory／migration／post-check／compare、catalog／RLS／audit negatives、atomic failure及lock timeout retry。
- `python -m tools.portal_data_phase_c_migration verify`：passed。
- `python -m tools.portal_data_phase_c_evidence verify`：passed。
- `python -m tools.portal_data_phase_c_readiness verify`：passed。
- `python -m compileall -q migrations tools tests/portal_data`：passed。
- `python -m black --check -W 1 tools/portal_data_phase_c_readiness.py tests/portal_data/test_phase_c_readiness.py`
  （`BLACK_CACHE_DIR`指向本機temp）：passed。
- Compose config分別以`postgres:15.8-alpine`及`postgres:16.4-alpine`解析：passed。
- `git diff --check`及staged diff check：passed。
- 測試完成後，兩個明確命名的TASK-074 containers、networks及fake-data volumes均已移除。

## 未執行與剩餘風險

- Branch已push至origin。Draft PR建立因本次對話缺少Owner對該外部操作的明確文字授權而停止，
  因此GitHub hosted matrix jobs尚未執行；取得授權並建立PR後，仍須以實際Actions結果確認workflow
  expression及兩個job名稱／logs。
- 未執行PostgreSQL 14 container；14以下與17以上由exact SQL expression及防放寬測試證明會輸出
  required false，畸形／未知CSV evidence由strict validator負向測試證明fail closed。
- 未取得新的production inventory，也未驗證production catalog、locks、role／BYPASSRLS風險、backup、
  transaction duration或runtime flags。TASK-073在exact merged commit回填並重新批准前仍不可執行。
- 本任務沒有修改migration source、schema語意、application behavior、environment variable runtime contract
  或deployment設定；只修改local test image selector及CI matrix。
- 工作目錄在實作commit後僅預期新增本report及HANDOFF交棒；無未說明的程式修改。

## Owner決策

目前不需要新的產品或migration決策。TASK-074通過Work review與hosted CI後，仍須由Owner依TASK-073
另行批准production read-only inventory及後續exact migration window。
