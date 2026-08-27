# TASK-164 Codex report

## Delivery delta

- 新增production Event migration operator，只允許`0008_mobile_notification_delivery`至`0009_event_management_writes`的單次Alembic transaction；以transaction advisory lock序列化，pre／post exact驗constraint、append-only trigger、Event tables RLS與zero policy。
- Append-only gate同時綁定`ntubtob` function schema、零參數、trigger return type、PL/pgSQL、canonical body SHA-256及版本穩定的trigger catalog邊界；enabled／event timing／row level、UPDATE OF columns／WHEN clause／constraint／transition tables／deferrability任一漂移均拒絕。
- `dry-run`使用read-only transaction且不執行migration；execute要求hidden short-lived acknowledgement，且以`pg_stat_xact_user_tables`驗證除Alembic revision外application-table DML為零。Already-forward、divergent、catalog drift與partial state全部fail closed，不提供retry。
- 新增no-disclosure launcher：dry-run與execute都只允許clean且HEAD=origin/main的exact merged `main`，execute再要求approved SHA；active gcloud account、exact project／region／service／Ready revision／100% traffic／runtime identity／public boundary與production flags／Secret-reference categories均須通過。Hidden URL只在記憶體中與Ready revision的DSN host／port／database／user逐欄比對，不讀既有private env或Secret payload。
- Repository authority baseline為`aa614ab57423f589d318bc96c627d5f5a1b61bb5`；Cloud target鎖定當前production rollback revision `web-portal-00051-p4z`，任何先行rollout或target drift均停止。
- Private URL只接受唯一scalar `sslmode=require|verify-ca|verify-full`；缺省、disabled、unknown、duplicate或額外query parameter均拒絕。
- Canonical-LF checksums與material manifest鎖定launcher、operator、既有0009 migration及其Alembic execution boundary；未修改0009或Web deployment wrapper。

## Verification

- `py -3.10 -m unittest tools.tests.test_production_event_management_rollout tests.portal_data.test_event_management_rollout -v`：14 unit passed；3 isolated PostgreSQL tests skipped（本機無`PORTAL_DATA_TEST_DATABASE_URL`／`PORTAL_DATA_DATABASE_URL`）。
- `py -3.10 -m unittest tests.portal_data.test_event_management_migration tests.portal_data.test_migration_readiness -v`：11 passed；6 isolated PostgreSQL tests skipped。
- `py -3.10 -m py_compile ...`：passed。
- Black formatter API逐檔比對4個Python owned paths：clean（Windows多檔CLI停滯後已終止本輪exact processes，未略過檢查）。
- `py -3.10 -m isort --check-only ...`：passed。
- `git diff --check`：passed。

## Remaining gates

- PostgreSQL 15／16 isolated integration、independent Data／Security review與hosted gate尚未完成；本report不授權或宣稱production migration／deployment。
- 未呼叫gcloud、未連線任何database、未讀Secret/private env、未部署、未修改production資料或發送通知。

## Hosted diagnosis

- PR #211 run `33084910566`的PostgreSQL 15／16都在0008 append-only precheck停止；migration尚未執行。根因是`pg_get_triggerdef(..., true)`固定輸出canonical event順序`BEFORE DELETE OR UPDATE`，而初版operator沿用migration source順序`BEFORE UPDATE OR DELETE`。
- PR #211第二次run `33085996379`的PostgreSQL 15／16仍在同一precheck停止，migration同樣未執行；這證明deparsed trigger definition不適合作為跨版本exact contract。
- 改為直接驗證版本穩定的`pg_trigger`／`pg_proc`目錄欄位：保留enabled／`tgtype=27`／function schema／args／return／language／body fingerprint，並新增`tgattr`、`tgqual`、`tgconstraint`、`tgoldtable`、`tgnewtable`、`tgdeferrable`、`tginitdeferred`的exact gates；移除`pg_get_triggerdef`字串依賴。修正後hosted PostgreSQL 15／16尚待重跑，不宣稱通過。
