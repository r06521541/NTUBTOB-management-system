# TASK-060：補齊 Phase A baseline marker 與 fail-closed RLS artifact

## 任務目標

將 Owner 已批准的兩項 Phase A 決策落成 deterministic、可審查、可在單一 transaction執行的 migration
artifact：

1. Production沒有 `ntubtob.alembic_version` 時，在同一 transaction建立 marker並記錄
   `0001_legacy_baseline`，再升級至 `0003_legacy_bigint_activity_game`；
2. 對全部13張新 portal-data tables enable RLS，Phase A建立零 policies並保持 application未啟用。

本任務只修改 repository、離線 verifier/tests與 local fake PostgreSQL rehearsal；不連線或修改 production。

## 已確認事實與 Owner 決策

- TASK-059即時唯讀 baseline：10張 legacy tables與 table/column/PK-FK fingerprints全部吻合；RLS 10/10；
  `ntubtob.alembic_version`不存在；13張 portal tables均不存在。
- SQL Editor session不是 superuser，但為 schema/legacy table owner，可 bypass RLS、create role/database並具完整
  legacy write privileges。
- Owner明確接受使用此 migration-owner role執行未來唯一 exact reviewed transaction。
- Owner明確決定 Phase A 對13張新 tables全部 enable RLS且建立零 policies。
- TASK-056/058已證明 retained production archive可驗證並隔離還原。
- 現有 artifact verifier可 deterministic重現 `0001 -> 0002 -> 0003` SQL，但 artifact只含 version UPDATE，
  無法處理 production marker缺席。

## 工作範圍

### 1. Baseline marker與單一 transaction artifact

- 建立 deterministic renderer，從同一 Alembic revision graph產生完整 Phase A artifact。
- Artifact必須 exactly one `BEGIN`／`COMMIT`，包含 transaction-local `lock_timeout='5s'`與
  `statement_timeout='60s'`。
- 在任何 portal DDL前，建立 `ntubtob.alembic_version`的 canonical Alembic table與PK，插入 exactly
  `0001_legacy_baseline`；接著只允許兩次 expected version UPDATE至0002、0003。
- 若 marker已存在、legacy fingerprints不符或 new portal objects已存在，production runbook必須要求 stop；
  artifact不得以 `IF NOT EXISTS`、upsert、delete或覆寫既有 marker繞過前置條件。
- Baseline create/insert與所有 expand DDL必須在同一 transaction；任何 failure/timeout必須連 marker一起 rollback。

### 2. RLS zero-policy contract

- 在 revision/source of truth中，對 exactly 13張新 portal tables執行 `ENABLE ROW LEVEL SECURITY`。
- 不建立 policy，不使用 `FORCE ROW LEVEL SECURITY`，不新增 GRANT/REVOKE，不改 legacy RLS。
- RLS DDL必須由 deterministic renderer納入 artifact，不得只手改 generated SQL。
- Phase A完成後新 tables為空，沒有 application reader/writer或backfill。

### 3. Static verifier補強

Verifier除既有檢查外必須 fail closed驗證：

- canonical marker table、PK與exact baseline insert只出現一次且順序在portal DDL前；
- exactly兩次 version UPDATE與最終revision 0003；
- exactly 13個 expected `ENABLE ROW LEVEL SECURITY`，零 policy、零 FORCE、零 grant/revoke；
- 不含 `IF NOT EXISTS`、upsert、marker delete/truncate、額外 insert/update或 arbitrary SQL；
- transaction、timeouts、approved CREATE/ALTER allowlists與 checksum仍 deterministic。

Mutation tests至少覆蓋 marker已跳過／重複／錯revision、partial baseline、missing/extra/wrong-table RLS、policy／
FORCE／grant注入、transaction split與checksum drift。

### 4. Local exact-shape rehearsal

使用既有10-table conspicuously fake local fixture實跑 exact artifact：

- clean no-marker baseline成功建立marker並升級至0003；
- 13張新 tables存在、空表、RLS enabled、not forced、policy count 0；
- 10張 legacy tables與fake row counts不變，只有 nullable `members.person_id` schema expand；
- injected mid-migration failure使 marker、13新表、Member column與所有partial objects一併 rollback；
- 5秒 lock timeout時 marker與schema無殘留，釋放lock後整包可從頭成功；
- pre-existing marker、任一 portal object或catalog drift在執行前 gate被拒絕，不自動修復／重跑。

不得以production archive、production rows或remote DB作 rehearsal。

### 5. Runbook／evidence同步

- 更新 production migration runbook為「marker create + baseline insert + expand」單一 exact transaction。
- 記錄 Owner接受 migration-owner high-privilege boundary；不記實際 role name。
- 記錄13新表 RLS enabled/zero policy、schema不在Data API exposed schemas、Phase A application access為none。
- 明確要求：TASK-060 merge後，Owner重跑 TASK-059 SQL；只有 fresh fingerprint／marker absence通過後才能提出
  production execution批准。
- 更新 evidence template、RLS decision package、Codex report與 HANDOFF。

## 非目標

- 不連 Supabase／production，不執行 production SQL、stamp、DDL、migration或read-only query。
- 不讀 credential／env file／DSN／role identity，不操作 Dashboard。
- 不建立任何 RLS policy、grant、runtime access或 application integration。
- 不做 Member/person/identity/event backfill，不部署服務、不發送通知。
- 不修改 Phase B/C產品規則、Web Portal routes、shared runtime models或production schema以外的無關程式。
- 不 push、PR、merge；除非 Owner在 Work驗收後另行批准 PR工作包。

## 驗收條件

- Canonical artifact可由 source deterministic重現，sidecar checksum一致。
- Static verifier與mutation tests證明 marker/RLS/transaction/allowlist fail closed。
- Local clean、mid-failure rollback、lock timeout/retry、pre-existing-state rejection全部通過。
- Local final state：revision 0003、13新表RLS enabled/not forced/zero policy且空、legacy fake counts不變。
- Python 3.10 tests、compile、Black/isort、Alembic graph/check、Docker Compose static check與`git diff --check`通過。
- 無 production／credential／remote／deployment／notification操作。

## 必要驗證

Codex應使用repository既有portal-data tests與local Compose gate，至少執行：

```powershell
python -m tools.portal_data_migration_readiness verify
python -m unittest discover -s tests/portal_data -v
python -m compileall -q tools migrations tests/portal_data
python -m black --check tools migrations tests/portal_data
python -m isort --profile black --check-only tools migrations tests/portal_data
docker compose -f docker-compose.portal-data.yml config
git diff --check
git status --short
```

Local integration需使用 fixed local-only URL gate與明顯假資料；完成後停止task-owned container，不刪除非本任務
資源。若Windows Python 3.10／formatter不可用，須明說並留給 hosted CI，不能宣稱已通過。

## 已知風險

- 修改既有 migration revision仍未部署production，因此可行；但必須同步deterministic artifact/checksum與所有
  callers/tests，不能只改SQL輸出。
- Table owner可 bypass RLS；zero-policy RLS保護非owner/client角色，但不限制已批准的migration owner。Phase C
  必須另行設計runtime role與policies。
- Fresh TASK-059 baseline將因本task耗時而必須重跑；本次已接受CSV不能直接授權production execution。

## Base commit

`84b589129e85c17e7247014dee3e8eb1060f4c7a`
