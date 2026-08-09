# TASK-051：建立 Production Portal Data Migration Readiness Package

## 目標

把 TASK-048 至 TASK-050 已驗證的 Person／角色／資格／Event expand schema，整理成可審查、
可離線重現且 fail-closed 的 production migration readiness package。成果必須讓 Owner 在真正
操作 Supabase 前，能看見 exact upgrade SQL、baseline／transaction／lock／RLS／backup／rollback
條件與仍待人工確認事項。

本任務只建立工作包與本機驗證工具，不連線 Supabase、不執行 production stamp、DDL、backfill
或部署。完成 TASK-051 也不代表 production migration 已獲批准。

## 背景與已確認事實

- PR #54 已 squash merge 為 `00c98866ecdb7c217bf47a7f8bc2a0873603348f`。
- TASK-049 的去識別 catalog 已確認 production PostgreSQL 15.1、`ntubtob` 10 張 legacy tables、
  legacy bigint identities、PK／FK／nullable／defaults 與所有 legacy tables 的 RLS enabled flags。
- Production 沒有 `ntubtob.alembic_version`；`0001_legacy_baseline` 是空 revision，任何 stamp 都必須
  在 exact catalog preconditions 通過後由 Owner 另案批准。
- TASK-050 已在 local exact fixture 通過完整 downgrade／rebuild／upgrade、35 項 tests 與
  `alembic check`；八張非 portal-data migration ownership 的 legacy tables 已排除於 autogenerate。
- `0002` 是 expand migration：新增 Person／identity／qualification／Event tables，並只對 legacy
  `members` 新增 nullable `person_id`、unique 與 FK；`0003` 把新建 `activities.game_id` 校正為 bigint。
- 目前 production request paths 尚未使用新 schema；production rollback 原則是保留 expand schema、
  回退 application，不執行 destructive downgrade。
- 尚未確認 production database runtime role、table ownership、Supabase API exposure、RLS policies、
  backup/PITR readiness、允許的 maintenance window 或可接受 lock timeout。

## 使用者價值

- 在任何正式 DDL 前把可執行內容、停止條件與人工責任一次說清楚。
- 防止把 local rehearsal command、destructive downgrade 或未審查的 autogenerate 誤用於 production。
- 將 expand schema、Member backfill、application rollout 分階段，降低既有網站、LINE 與排程服務風險。
- 為後續角色權限與多元活動正式上線建立可稽核的資料層入口。

## 工作範圍

### 1. Upgrade-only SQL artifact

- 以已合併的 `0001 -> 0002 -> 0003` revision chain 產出 deterministic、可 code review 的
  upgrade-only PostgreSQL SQL artifact，保存於 `docs/operations/sql/`。
- SQL 必須明確包含 transaction boundary，且不得包含 downgrade、`DROP`、`TRUNCATE`、資料列
  `DELETE`／`UPDATE`、backfill、production credentials 或 application row values。
- 除 Alembic version bookkeeping 外，不得加入未被現有 revisions 表達的 production DDL。
- 明確列出唯一會改動的 legacy table：`members`；`activities` 是同一工作包中新建後校正的 table。
- 若 Alembic offline rendering 不能穩定產生符合上述條件的 artifact，應建立小型、可測試的
  repository-only renderer；不得建立接受 remote DSN 或直接 execute SQL 的工具。

### 2. Static migration safety verifier

建立 Python 3.10-compatible 的離線 verifier，至少驗證：

- revision graph exactly 是 `0001_legacy_baseline -> 0002_portal_data_foundation ->
  0003_legacy_bigint_activity_game`，沒有 branch／multiple heads。
- upgrade artifact 只建立核准的新 tables、indexes、function、triggers、constraints，以及核准的
  `members.person_id` 變更。
- artifact 不含 destructive／DML／credential／remote-host pattern。
- catalog-owned legacy tables 不會被 drop 或被非預期 alter。
- artifact 與 revisions 不一致時 fail closed，並只輸出固定分類錯誤，不輸出 DSN 或 SQL secrets。

Verifier 預設只讀 repository files；不得讀 `envs/**/.env.yaml`，不得連 DB 或網路。

### 3. Local production-shape rehearsal

延伸既有 local PostgreSQL tests／工具，以 exact fake legacy fixture 驗證：

- baseline preconditions、stamp `0001`、upgrade head 與 `alembic check`。
- migration 在單一 transaction 中間故意失敗時，不留下半套 new tables、Member column 或 version row。
- 以第二連線持有 `members` 相衝突 lock，執行 migration 時能在 bounded lock timeout 內停止；釋放 lock
  後可重新完整執行，不產生 drift。
- migration 前後所有 10 張 legacy tables 與 fake legacy row counts 保持不變；只允許
  `members.person_id` schema 擴張，不做 Member backfill。
- upgrade 成功後新 tables 為空，且 existing services/functions 不會自動讀取或寫入它們。

不得以 sleep-heavy 或不穩定 timing assertion 實作；lock 測試應使用明確 transaction／synchronization。

### 4. Production runbook 與 evidence template

新增 `docs/operations/data/PORTAL_DATA_PRODUCTION_MIGRATION_RUNBOOK.md`，至少包含：

1. exact commit／SQL checksum／migration head 鎖定方式；
2. 執行前 read-only catalog fingerprint 與 `alembic_version` absence preconditions；
3. Owner 必須在 Supabase 親自確認或提供的 backup／PITR、maintenance window、runtime DB role、
   table owner、API exposure 與連線池資訊；
4. baseline stamp 與 expand upgrade 的順序、transaction、`lock_timeout`／`statement_timeout` 原則；
5. 成功條件、失敗分類、停止條件與可保存但不得含 secret／row values 的 evidence；
6. rollback/recovery：transaction 未 commit 則驗證自動 rollback；commit 後保留 expand schema，
   不執行 production downgrade；必要時回退尚未切換的新 application；
7. Phase A schema expand、Phase B Member/identity backfill、Phase C application opt-in 的明確分隔；
8. 每一階段需要 Owner 的精確授權文字範本，但範本本身不構成授權。

另提供空白、去識別化 evidence template，不得預填 production account、host、project、role、size、
row value、Secret 或連線字串。

### 5. RLS 與角色決策包

- 依新 tables 分類資料敏感度、預期 writer／reader 與最小能力，但明確區分「已確認」與「待確認」。
- 提供至少兩個可比較方案：
  - migration 時先 enable RLS、zero policy/fail closed，application 暫不啟用；
  - schema expand 先保持 service-private access，待 exact runtime role 與 policies 驗證後再 enable RLS。
- 分析各方案對 table owner、service connection、Supabase API exposure 與 rollout 的風險。
- 不替 Owner 選定 production RLS policy，不把假設寫入 executable migration。

### 6. 文件同步

- 修正 `migrations/README.md` 與 `docs/development/LOCAL_PORTAL_DATA.md` 中已過時的 minimal
  two-table fixture 說明，使其符合 TASK-050 的 10-table exact fake fixture。
- 更新 Codex report、`PROJECT_STATE.md` 與 `HANDOFF.yaml`，但遵守 commit 精簡規則。

## 明確非目標

- 不連線或查詢 Supabase／production DB，包括 read-only 連線。
- 不執行 production Alembic stamp、DDL、SQL、backfill、RLS policy 或 privilege 變更。
- 不讀取／顯示 Secret、`.env.yaml`、DSN、database password 或 production role 名稱。
- 不新增可接受 remote URL、可直接執行 production SQL或可繞過人工確認的一鍵 migration 工具。
- 不修改現行 Web Portal、LINE webhook、排程服務的 request path、runtime requirements 或部署設定。
- 不實作 Member／identity backfill，不決定 legacy `ignored` 映射為 `blocked` 或 `disabled`。
- 不建立角色管理 UI、Event CRUD、通知、Google／Apple OAuth 或 Flutter 功能。
- 不部署、人工 invoke、push、建立 PR、merge 或修改任何雲端資源。

## 設計與安全要求

- Python 3.10 相容；測試使用明顯虛構資料。
- 所有 DB integration 只能通過既有 local database gate，僅允許
  `ntubtob_portal_local` 與 localhost／Compose service。
- Production SQL artifact 必須由已審查 revision chain deterministic 產生或具等價 drift test，
  不得手工維護兩份無一致性檢查的 DDL。
- migration 的 production execution path 在本任務中必須不存在；文件中的命令應清楚標記
  `DO NOT RUN WITHOUT OWNER APPROVAL`。
- 不以測試通過推定 production lock、RLS、backup、role 或 API exposure 正確。

## 驗收條件

1. upgrade-only SQL artifact 可重現，checksum 穩定且與 revision chain 一致。
2. verifier 對正常 artifact 通過，對 DROP／DML／額外 legacy ALTER／remote credential pattern mutation
   均 fail closed。
3. local exact fixture 的 stamp、upgrade、`alembic check` 與 35 項既有 portal-data tests 持續通過。
4. mid-migration failure 驗證 transaction atomicity，不留下 partial schema 或 version state。
5. bounded lock contention 測試會停止且可安全重試；不依賴長時間 sleep。
6. migration 前後 legacy fake row counts 不變，新 tables 為空，沒有 backfill。
7. runbook 完整覆蓋 preflight、backup/PITR、baseline、timeout、evidence、success、stop、recovery 與三階段 rollout。
8. RLS 文件清楚區分可選方案、已確認事實與 Owner／production 待確認事項。
9. 文件已移除過時的 two-table fixture 敘述。
10. Python 3.10 tests、compile/import、`alembic check`、static verifier 與 `git diff --check` 通過。
11. Codex report 明說沒有 production connection、DDL、stamp、backfill、Secret、cloud、通知、push、PR、merge 或 deployment。

## 必要驗證命令

Codex 應依實際工具名稱補齊，但至少執行：

```powershell
docker compose -f docker-compose.portal-data.yml config
docker compose -f docker-compose.portal-data.yml up -d portal-postgres
$env:PORTAL_DATA_DATABASE_URL = "postgresql+psycopg2://portal_local:local-only-password@127.0.0.1:55432/ntubtob_portal_local"
py -3.10 -m tools.setup_portal_data_legacy
py -3.10 -m alembic stamp 0001_legacy_baseline
py -3.10 -m alembic upgrade head
py -3.10 -m alembic check
py -3.10 -m unittest discover -s tests/portal_data -v
py -3.10 -m compileall -q shared_lib/shared_module tools migrations tests/portal_data
git diff --check
git status --short
```

驗證結束後停止 task-owned container；保留 named volume，除非明確證明只刪除本任務 Compose volume。

## 主要預期變更

- `docs/operations/sql/` 的 upgrade-only artifact
- `docs/operations/data/PORTAL_DATA_PRODUCTION_MIGRATION_RUNBOOK.md`
- 去識別化 evidence template 與 RLS decision package
- repository-only SQL renderer／verifier 及 tests
- local PostgreSQL atomicity／lock／no-data-change regression tests
- `migrations/README.md`、`docs/development/LOCAL_PORTAL_DATA.md`
- `docs/coordination/reports/TASK-051-CODEX.md`

## 交付與 commit 規則

- 主要成果使用描述性 commit，例如：
  `feat(portal-data): prepare fail-closed migration readiness package`
- report、驗證證據與 handoff 優先併入同一成果或單一 completion commit，不為狀態往返建立多個 commits。
- 完成後更新 `HANDOFF.yaml` 為 `ready_for_review / work`。
- 本任務未授權 push、PR、merge、production connection、migration 或 deployment。

## Base commit

`00c98866ecdb7c217bf47a7f8bc2a0873603348f`
