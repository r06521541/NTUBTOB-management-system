# TASK-050 Codex report

## 範圍與提交

- base commit：`b5689ec`
- implementation commit：`d2b7b848289d702b4c166f61a576ccb516c79555`
- 範圍：只實作 local PostgreSQL legacy fixture、`bigint` migration/model fidelity 與
  append-only attendance history 的 deterministic current-state projection。

## 實作結果

- `tools/setup_portal_data_legacy.py` 現在依 TASK-049 去識別 catalog 建立 10 張 fake legacy
  tables，含欄位型別、nullable/default、FK、`bigint` identity 及 RLS enabled metadata。
  fixture 使用明顯虛構資料，涵蓋 linked、pending、ignored LINE user、一般及已取消 game、
  state change、same-reply history，以及空的 `cancellations` table。
- 新增 `0003_legacy_bigint_activity_game`，不改寫已合併的 `0002`，將 local rehearsal 的
  activity-to-game relation 升級為 `bigint`。downgrade 僅供 isolated local rehearsal 使用；
  production rollback 仍應回退 application、不 destructive downgrade expand schema。
- `LegacyMemberRecord`、`LegacyGameRecord` 與 `ActivityRecord.game_id` 已改為 `BigInteger`。
- 新增 read-only `project_current_attendance()`，固定以 `(updated_at, id)` 選取各
  `(game_id, member_id)` 的最後版本；不寫入、不刪除且不對 legacy table 新增 unique constraint。
- PostgreSQL tests 現可在既有 `PORTAL_DATA_DATABASE_URL` local gate 下執行，並驗證 fixture、
  FK、RLS、空 cancellations、downgrade/rebuild/upgrade、backfill idempotency 與投影規則。

## 驗證

以下均以 local Docker PostgreSQL（`127.0.0.1:55432/ntubtob_portal_local`）執行：

```powershell
docker compose -f docker-compose.portal-data.yml config
docker compose -f docker-compose.portal-data.yml up -d portal-postgres
$env:PORTAL_DATA_DATABASE_URL = "postgresql+psycopg2://portal_local:local-only-password@127.0.0.1:55432/ntubtob_portal_local"
py -3.10 -m tools.setup_portal_data_legacy
py -3.10 -m alembic stamp 0001_legacy_baseline
py -3.10 -m alembic upgrade head
py -3.10 -m alembic current
py -3.10 -m unittest discover -s tests/portal_data -v
py -3.10 -m compileall -q shared_lib/shared_module tools migrations tests/portal_data
git diff --check
```

結果：全部通過；portal-data suite 為 35 tests。rehearsal test 額外完成
`0001 -> head -> 0001 -> fixture rebuild -> head` 的可重現性驗證。

首次使用 Python 3.10 時發現該環境缺少既有的 SQLAlchemy/Alembic dependencies；已僅安裝
repository 既有 requirements 以執行本機驗證。完整 root requirements 安裝因本機 C 槽剩餘空間
不足而中止，但 migration-specific requirements 安裝成功，未改動 repository 依賴檔。

## 安全與未驗證事項

- 未連線、查詢、stamp、DDL、backfill 或寫入 Supabase production。
- 未讀取或處理任何 `.env.yaml`、connection string、token 或 Secret。
- 未部署、push、建立 PR、呼叫外部 API 或發送通知。
- 本機 RLS 僅驗證 enabled metadata；production RLS policies、database role、API exposure、
  baseline stamp、lock time、PITR/backup 與 production deployment compatibility 仍未驗證。
- ignored legacy LINE user 對新 identity 的 `blocked`／`disabled` 映射仍保留給 Owner 核准的
  後續 backfill task。

## Work 補正（2026-08-07）

Work 發現 `alembic check` 會把未建模的 legacy tables 視為可刪除物件，並偵測
`members`／`games` metadata drift。已在 commit
`1a17cb04a0e1700ebedf0c674b72416090354743` 補正：

- `LegacyMemberRecord` 與 `LegacyGameRecord` 對齊 catalog 的 identity、`smallint`、nullable
  與 timezone-aware metadata。
- `migrations.env` 明確將八張未由 portal-data migration 管理的 legacy tables 排除在
  autogenerate ownership 外；它們不會再被建議 drop。
- local rehearsal regression 現會執行 `command.check(config)`。

在全新 local Docker database 重新驗證：`py -3.10 -m alembic check` 與測試內的
`command.check(config)` 均回報 `No new upgrade operations detected`；35 項 portal-data tests、
`compileall` 與 `git diff --check` 通過。未連線 production、未讀取 Secret、未執行任何
production schema action。
