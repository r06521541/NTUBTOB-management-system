# TASK-164 Codex report

## Delivery delta

- Recovery lease 2將production operator重建為只允許exact `0004_phase_c_identity_lifecycle`至`0009_event_management_writes`的單次Alembic transaction；以transaction advisory lock序列化，precheck以既有accepted catalog fingerprints鎖定Event／Phase C touched columns、所有constraints（含access-audit action）與indexes及0005–0008 future-object absence；postcheck exact revision、column attributes/default/identity、constraints/FKs/checks、btree indexes/order/predicate、RLS／zero-policy／new-table emptiness。
- Append-only gate同時綁定`ntubtob` function schema、零參數、trigger return type、PL/pgSQL、canonical body SHA-256及版本穩定的trigger catalog邊界；enabled／event timing／row level、UPDATE OF columns／WHEN clause／constraint／transition tables／deferrability任一漂移均拒絕。
- `dry-run`使用read-only transaction且不執行migration；execute要求hidden short-lived acknowledgement，且以`pg_stat_xact_user_tables`驗證除Alembic revision外application-table DML為零。Already-forward、divergent、catalog drift與partial state全部fail closed，不提供retry。
- 新增no-disclosure launcher：dry-run與execute都只允許clean且HEAD=origin/main的exact merged `main`，execute再要求approved SHA；active gcloud account、exact project／region／service／Ready revision／100% traffic／runtime identity／public boundary與production flags／Secret-reference categories均須通過。Hidden URL只在記憶體中與Ready revision的DSN host／port／database／user逐欄比對，不讀既有private env或Secret payload。
- Repository recovery branch base為`39be8134739c2b0881e522af851c2973780d2027`；Cloud target鎖定當前production rollback revision `web-portal-00051-p4z`，任何先行rollout或target drift均停止。
- Private URL只接受唯一scalar `sslmode=require|verify-ca|verify-full`；缺省、disabled、unknown、duplicate或額外query parameter均拒絕。
- Canonical-LF checksums與material manifest鎖定launcher、operator、既有0005–0009 migrations及其Alembic execution boundary；五個migration均無application-table DML，未修改migration或Web deployment wrapper。

## Verification

- `py -3.10 -m unittest tools.tests.test_production_event_management_rollout tests.portal_data.test_event_management_rollout -v`：22 unit passed；6 isolated PostgreSQL tests skipped（本機無`PORTAL_DATA_TEST_DATABASE_URL`／`PORTAL_DATA_DATABASE_URL`）；PG regressions涵蓋wrong-table Phase C constraint，以及target column type/default/identity generation、constraint definition/boolean grouping、FK update action、index、function body/security與trigger漂移。
- `py -3.10 -m unittest tests.portal_data.test_event_management_migration tests.portal_data.test_migration_readiness -v`：11 passed；6 isolated PostgreSQL tests skipped。
- `py -3.10 -m py_compile ...`：passed。
- Black formatter API逐檔比對4個Python owned paths：clean（Windows多檔CLI停滯後已終止本輪exact processes，未略過檢查）。
- `py -3.10 -m isort --check-only ...`：passed。
- `git diff --check`：passed。

## Remaining gates

- Independent Data／Security reviewer經五輪adversarial review後`ACCEPT`；PostgreSQL 15／16 isolated hosted gate尚未完成。本report不授權或宣稱production migration／deployment。
- 未呼叫gcloud、未連線任何database、未讀Secret/private env、未部署、未修改production資料或發送通知。

## Recovery source evidence

- Main以既有受控唯讀inventory確認`classification=REVISION_VERIFIED_READ_ONLY`、`current_revision=0004_phase_c_identity_lifecycle`、`mutation_count=0`；本report只記去識別化分類，不含database target或credential。此證據解除lease 1的錯誤0008 source premise，並精確支持lease 2的0004→0009 recovery contract。

## Lease 2 review corrections

- Independent review要求postcheck不得只驗object名稱。修正後column fingerprint包含identity generation；FK包含exact referenced schema/relation、delete/update/match；CHECK與partial-index expression使用total lexer及保留AND/OR樹狀分組的canonical fingerprint，精確保留quoted literal大小寫、否定regex operator與signed number，任何未消耗token/cast均fail closed；function identity另綁定kind、set-returning、security definer、volatility、strict、leakproof、parallel、config、default args及variadic旗標，trigger並以function schema與已驗證function OID關聯。這些gate拒絕跨schema同名table/function替換，均保留原有fail-closed邊界且未修改migration。
- Hosted run `33145074357`的PostgreSQL 15／16均在target schema postcheck以`future migration check definition drifted`停止。原因是migration中的三個`BETWEEN` checks經PostgreSQL parse tree／`pg_get_expr`正規化為等價的`>= lower AND <= upper`，而repository expected fingerprint仍保留`BETWEEN` leaf。Canonicalizer現在只對布林層分割後含單一、完整top-level `subject BETWEEN lower AND upper`的節點建立同一個AND AST；缺subject／lower／upper、未分組chained/multiple BETWEEN或未知token均fail closed，分組後的多個合法BETWEEN仍可各自正規化。Regressions涵蓋真實deparsed等價、changed bound/grouping不等價與所有malformed shapes。Run中的後續drift cases因同一baseline mismatch被遮蔽，不能視為其獨立結果；修正後hosted matrix尚待重跑。
- Hosted run `33145963873`確認clean baseline在PostgreSQL 15／16均已通過；剩餘失敗只來自兩個test defects：constraint drift fixture將實際`ck_mobile_sessions_status`誤拼為singular，導致mutation前即`UndefinedObject`；disabled trigger由verifier正確分類為`trigger definition drifted`，而test誤期待`trigger fingerprint`。本輪只修正fixture名稱與expected reason，未改verifier或migration；完整matrix仍待重跑。

## Lease 1 hosted diagnosis

- PR #211 run `33084910566`的PostgreSQL 15／16都在0008 append-only precheck停止；migration尚未執行。根因是`pg_get_triggerdef(..., true)`固定輸出canonical event順序`BEFORE DELETE OR UPDATE`，而初版operator沿用migration source順序`BEFORE UPDATE OR DELETE`。
- PR #211第二次run `33085996379`的PostgreSQL 15／16仍在同一precheck停止，migration同樣未執行；這證明deparsed trigger definition不適合作為跨版本exact contract。
- 改為直接驗證版本穩定的`pg_trigger`／`pg_proc`目錄欄位：保留enabled／`tgtype=27`／function schema／args／return／language／body fingerprint，並新增`tgattr`、`tgqual`、`tgconstraint`、`tgoldtable`、`tgnewtable`、`tgdeferrable`、`tginitdeferred`的exact gates；移除`pg_get_triggerdef`字串依賴。修正後hosted PostgreSQL 15／16尚待重跑，不宣稱通過。
- PR #211第三次run `33086683742`的PostgreSQL 15／16仍在同一precheck停止，migration再次未執行；本機Docker daemon／PostgreSQL不可用，因此不猜測catalog實際值。所有gate保持不變，只將mismatch分為不含原始值的固定reason：`trigger_core|trigger_columns|trigger_when|trigger_constraint|trigger_transition|trigger_deferrability|function_identity|function_body`，供下一次hosted run定位。
- PR #211第四次run `33087231730`的fixed reason證明catalog gates全數通過；PostgreSQL 15／16均在entry absolute-zero DML gate以`transaction contains prior application DML`停止，migration仍未執行。根因是integration `setUp`完成fixture與0008 upgrade後立即重用同一pooled backend；測試現在於setup完成後dispose pool，強制operator使用fresh backend，production operator的absolute-zero entry gate未改動。
