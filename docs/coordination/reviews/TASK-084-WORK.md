# TASK-084 Work review

## 驗收範圍

- Branch：`codex/phase-c-final-closeout`
- Implementation：`d4d0152`
- Reviewed HEAD：`5370a6774ce898c7ba13c86d2e76109db03c2d62`
- Repository：驗收開始時乾淨

## 已確認通過

- 新 SQL 有固定 checksum，使用 read-only transaction、local timeouts，未含 DDL/DML。
- closeout manifest 固定 runtime service vector、IAM classification、traffic、Phase C／freeze／maintenance 欄位，並拒絕未知欄位與敏感字樣。
- `ignore`／`unignore` domain action 對 pending、unlinked LINE identity 具 transaction、audit 與 request-ID idempotency 保護。
- Work 獨立重跑 Phase C closeout／rollout／transition-controller suite：19/19 passed。

## Blocking findings

### 1. Inventory evidence 尚無可重現的 strict ingestion／compare path

`TASK-084-phase-c-closeout-inventory.sql` 只輸出 revision、identity count、粗略 candidate count、audit count、duplicate request count與 active team-player count；`build_manifest()` 卻要求 admin principal、三類 drift與 safe candidate count。Runbook 目前要求操作者另跑 TASK-068 並手工組合 evidence，但沒有 parser、欄位映射、CLI 或 before／after comparer。因此 Stage B 無法由固定 artifact 重現，也無法證明輸入 manifest 的數字確實來自兩份核准 SQL。

請補一條 fail-closed、可離線測試的 ingestion／comparison path：解析固定六欄 CSV、拒絕缺列／重複列／未知列／型別錯誤，從明確 metrics 導出 manifest，並能比較 before、mutation、idempotent retry、recovery、post-check 的精確 audit delta與保護性 counts。

### 2. 現有 safe candidate SQL 分類比 domain precondition 寬

SQL 只檢查 `auth_identities.status='pending' AND person_id IS NULL`，但正式 `set_ignored()` 還要求對應 legacy LINE row 存在、`member_id IS NULL`，且目前 ignored state 必須符合要執行的方向。這個 count 可能包含實際無法執行／恢復的 row。

請讓 aggregate candidate classification 精確對齊 `set_ignored()`：LINE provider、pending、no Person、matching legacy row、no Member，並分開計算目前可 ignore 與可 unignore 的數量；不得輸出 identifier。

### 3. TASK-068 audit gate 無法直接作為 mutation 後 post-check

`TASK-068-identity-drift-inventory.sql` 將非 Phase-B backfill 的 audit 全部計入 `unexpected_audit_count`，其 verifier要求該值為零。TASK-084 一旦成功執行 `identity_ignored`／`identity_unignored`，重新跑 TASK-068 必然把核准的新 audit 判成 drift。現有 runbook 卻要求 mutation 後重跑「both inventories」，流程會在成功路徑自我阻擋。

請建立 TASK-084 專用、仍 fail-closed 的 post-check audit contract：允許且只允許兩個 Owner 核准 request ID 對應精確 action sequence，其他既有 Phase-B audit consistency與跨模型 drift仍須保持；不得放寬 TASK-068 歷史 verifier。

### 4. Admin allowlist 與 idempotent HTTP retry 需要精確可執行步驟

正式 admin 是「active Person + linked identity + Member ID 位於 runtime allowlist」，不是單看 `people.portal_access_level='admin'`。Runbook目前只有抽象的 classified count，尚未說明如何在不輸出 ID／env payload下取得此證據。另外，同一 request ID retry 雖由 route/domain支援，但 UI redirect後會產生新 nonce；runbook必須固定一個可重現且不把 target/request ID寫入 repository、shell history或一般 log的執行方法，並明確驗證第一次、同 ID retry、不同 ID recovery的 audit delta。

請補安全的 operator input boundary與離線 route/domain regression，證明完全相同 POST 可重送且第二次不新增 audit；不得新增繞過 CSRF／admin／maintenance gate 的專用 production endpoint。

## 驗收結論

`changes_requested`。目前基礎 verifier 與文件方向正確，但尚不足以安全進入 Stage B；上述問題都屬 production closeout 執行鏈的可重現性與 fail-closed 邊界，不是非阻擋文件建議。

下一位：Codex。

## 第二輪補正驗收（`f9558be`／`9613bab`）

### 已修正

- candidate SQL 已精確加入 LINE provider、pending、no Person、matching legacy row、no Member，並拆分 ignore／unignore counts。
- 已新增 CSV row ingestion 與 audit count sequence 的初步 verifier。
- runbook 已明記 admin classification 與相同 POST retry 不得繞過既有安全 gate。
- Work 重跑 closeout tests：5/5 passed。

### 仍為 blocking

1. **Parser 無法解析其對應 SQL 的完整輸出。** SQL 固定輸出 `identity_count`，但 `CSV_METRICS` 未宣告該 metric；把完整合法 rows 傳入 `ingest_inventory_rows()` 會得到 `CloseoutEvidenceError: inventory CSV metric is invalid`。此外 `csv` import 未實際提供 CSV text/file parsing入口，`status` 欄也未驗證，active team-player count解析後被丟棄。請以真實 SQL 的完整固定 row contract 建 table-driven fixture，確認完整合法輸出可進、任何 missing／duplicate／unknown／wrong-status／wrong-null-placement／bad-type 均 fail closed。
2. **Sequence verifier 尚未驗證 bounded action sequence。** 現在只比較 audit總數 `+1 / +0 / +1`，沒有輸入或驗證 Owner 核准的兩個 request IDs、`identity_ignored`／`identity_unignored` action counts、同一 target classification，其他任意兩筆 audit 也能通過。請讓 sanitized SQL／ingestion提供兩個外部 request ID 的精確 action aggregate（不輸出ID本身），並驗證 action、retry零增量、recovery action與最終 ignore/unignore candidate counts恢復；不得只依 global audit count。
3. **外部 drift/admin 數值仍是未驗證的任意整數。** `admin_principal_count`與三個 drift count可由 caller任意傳入，沒有固定來源 mapping或交叉檢查；runbook也只說 operator「must confirm」。請提供固定、可重現的 sanitized來源／ingestion contract，尤其 admin必須符合 active Person + linked identity + runtime allowlisted Member，而不是 portal access level。Owner提供的 allowlist只能在安全執行環境作為參數／stdin，不可輸出或寫入 repository。
4. **Same-POST retry步驟仍不可直接照 runbook執行。**「在 following redirect 前 replay exact POST」未指定受支援的瀏覽器操作或工具，正常 form navigation通常自動 follow redirect。請建立不保存 cookie、CSRF、target或request ID、不寫 shell history的明確操作程序，或以現有瀏覽器可重現步驟說清楚；並增加 Web Portal route regression，實際以完全相同 POST兩次驗證 domain第二次不新增audit且安全 decorators仍生效。

第二輪結論仍為 `changes_requested`。未進行 production inventory 或 mutation。

## 第三輪補正驗收（`74d3793`／`5f6bbed`）

### 已確認通過

- SQL metric set與parser exact set已綁定；完整fixture及missing／duplicate／unknown／wrong status／null placement／bad type反例皆有測試。
- admin與基礎drift數值不再由任意caller整數注入。
- Web Portal route已測完全相同POST兩次仍通過原有session、admin、CSRF、Phase C與maintenance gates；domain PostgreSQL regression已加入hosted path。
- Work重跑closeout suite：6/6 passed；route targeted測試需依該service既有working-directory方式執行，Codex完整file suite 63 passed證據可接受，final hosted CI仍須補證。

### Remaining blocking findings

1. **TASK-068 post-check矛盾仍未解除。** Runbook仍要求動作後「Re-run both inventories」。但TASK-068 verifier固定要求`unexpected_audit_count=0`，而成功smoke必然新增`identity_ignored`與`identity_unignored`，因此合法成功路徑仍會被TASK-068判失敗。新的三個drift count也只涵蓋duplicate identity、unlinked Member與orphan qualification，沒有涵蓋TASK-068的missing/wrong identity、orphan legacy link、team-player missing/extra/revoked等完整跨模型規則。請建立一條可執行且單一真實來源的post-check：重用完整TASK-068非audit drift規則，但audit consistency明確允許且只允許本次bounded pair；不要要求執行一個已知必敗的舊verifier。
2. **Recovery尚未綁定同一target。** SQL只分別計算兩個request ID的action count，沒有驗證兩筆audit的`auth_identity_id`相同。對identity A ignore、對identity B unignore，配合其他候選變動，仍可能通過aggregate gate。請新增只輸出boolean/count的same-target join classification，並要求為exactly one；不得輸出target ID。
3. **Candidate counts需驗證精確delta。** 現在只要求before ignore>=1、action後unignore>=1、retry不變、post恢復；未要求action後`safe_ignore=-1`且`safe_unignore=+1`。請固定精確delta並在retry snapshot要求兩種candidate counts都不變，降低並行或錯target被aggregate掩蓋的風險。
4. **psql輸入邊界需修正文案或方法。** `\prompt`避免shell history與repository file，但不是masked input，且psql variable substitution可能把literal放進送往server的statement；不可宣稱request IDs／allowlist「不輸出／不記錄」而沒有驗證server statement logging boundary。請改為準確威脅模型與執行前log-setting stop condition，或採不把這些值嵌入SQL statement的可重現方法。實際值仍不得寫入repository、一般terminal transcript或交接摘要。

第三輪結論：`changes_requested`。其餘Stage A方向可保留；未進行production操作。

## 第四輪補正驗收（`9fa4401`／`4b63b08`）

### 已確認通過

- 單一五快照流程已明確區分before／action／retry／recovery／post。
- 完整TASK-068 identity、Member/Person與team-player non-audit drift規則已納入新SQL，不再要求合法smoke後執行必敗的舊audit verifier。
- bounded audit pair已要求精確actions、same target與兩個不同request-ID分類。
- candidate counts已要求action精確`-1/+1`、retry不變、recovery/post完整復原。
- psql substitution與provider/server logging風險已如實記錄，unsafe／unknown均stop。
- Work獨立重跑closeout／rollout／transition suites：22/22 passed；`git diff --check` passed。

### 最後兩項 blocking 收斂

1. `compare_sequence()`只驗證每個snapshot各自是all-on/unfrozen/100%，未要求五個snapshot的完整runtime evidence完全相同。服務revision可在中途改變而仍通過。請要求before的三服務revision、traffic、IAM、Phase C、freeze與maintenance vector在五個snapshot精確一致，並加反例。
2. TASK-084完成定義要求Member links、qualifications、attendance與notification counts無非預期差異。SQL雖讀取`identity_count`與`active_team_player_count`，ingestion卻丟棄兩者，sequence也未比較；且未讀取`member_count`、`people_count`、`reliable_linked_line_count`與`game_attendance_replies` count。請加入這些去識別aggregate並要求五快照一致。Identity ignore/unignore不應改動通知資料；由於LINE notify tokens已棄用且本動作無通知caller，不需重新引入該legacy table，只需在runbook／manifest明確把notification invariant記為「無通知路徑＋production notification log/error分類」，不可虛構DB notification count。

完成這兩項即可進final Stage A PR/hosted gate；不要求再擴張工具或新增功能。

## Stage A 最終驗收（`6c91a02`／`d7fca44`）

- 五快照完整runtime vector現要求逐欄精確一致，合法格式但不同revision的反例會fail closed。
- People、Member、identity、reliable LINE、active team-player及game attendance reply aggregate均由checksummed SQL導出並在五快照逐次比較。
- Notification boundary正確維持為domain no-caller與後續核准的production error/log classification，未重新引用已棄用`line_notify_tokens`。
- Work獨立重跑Phase C closeout／rollout／transition suites：23/23 passed。
- `compileall`與`git diff --check`通過；repository除本Work review外無未說明變更。
- 未執行production inventory、gcloud、DB、build/deploy、flag、traffic、IAM、Scheduler或通知操作。

Stage A本機驗收結論：`accepted`，等待唯一ready PR的hosted Python 3.10與PostgreSQL 15／16 final gate。Hosted gate通過且branch未再改變後可依standing Git authorization squash merge；Stage B production唯讀inventory仍須Owner另行精確批准。

## Stage B pre-execution security finding（2026-08-09）

- PR #84已通過hosted gate並merge為`10cc550`；Windows CRLF checksum prerequisite亦經PR #85通過並merge為`afee2e3`。
- Owner批准Stage B後，GCP唯讀inventory確認三服務Ready／100% traffic、Phase C all-on、freeze all-off、maintenance off、IAM與Secret binding metadata符合既有部署契約；未讀Secret值，最近精確revision ERROR與兩個Scheduler job metadata-only log查詢無紀錄可回傳，分類為unavailable而非成功流量證據。
- 執行production SQL前，Work查證Supabase官方文件：平台提供Postgres／Supavisor logs，且`pg_stat_statements`保存representative statement。現有psql `:'var'`會把allowlist及request IDs替換進server-bound SQL文字；只檢查`log_statement`／pgAudit不足以證明其他provider／statistics層不保存literal。
- PostgreSQL 16支援psql `\bind` extended query protocol，可將SQL placeholders與參數值分離。為符合既有「不得將target／request ID寫入log」邊界，production SQL執行暫停，須先將controlled query改成`$1/$2/$3` parameter binding並加入offline contract／checksum／runbook驗證。不得以放寬logging假設繞過。

結論：`changes_requested / codex`。既有Stage B批准仍有效，但在參數化prerequisite merge前不得執行production DB inventory；已完成的GCP唯讀證據不構成任何mutation授權。

## Parameter-binding review（`78dfc0a`／`9bfe93d`）

### 已確認通過

- Controlled query只使用`$1/$2/$3`，固定一個`\bind`順序後以extended query protocol執行；舊colon interpolation、literal request ID、錯誤bind數量／順序均有fail-closed tests。
- `BEGIN TRANSACTION READ ONLY`、local timeouts、`ROLLBACK`、strict metrics與canonical checksum均保留。
- Work獨立重跑closeout／rollout／transition suites：23/23 passed；`git diff --check` passed。

### 唯一remaining blocking

Runbook Docker command尚不可安全／可重現執行：`<owner-approved-read-only-connection>`可能把DSN放入argv；container沒有read-only mount repository，故`\i docs/...sql`找不到artifact；image使用mutable tag且沒有`--pull never`；也未使用Owner既有批准的private env-file與`default_transaction_read_only=on`連線級防線。

請只修operator command及contract test：沿用TASK-056已驗證的PostgreSQL 16 image digest `sha256:89ec47deeeddac28eb60b5672a456c54213ff4528f8752fda7f7c2a0e4ead36a`與`--pull never`，以`--env-file C:\Users\USER\.ntubtob-private\backup.env`載入PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD（不得讀檔），將exact repository root唯讀掛載至container並設定workdir，使`\i`可讀controlled SQL；加入非機密`PGOPTIONS=-c default_transaction_read_only=on`。禁止DSN／password／host/user出現在argv或文件。SQL與verifier其他行為不要再改。

結論仍為`changes_requested / codex`；修正此唯一operator boundary後可進PR。

## Docker operator final review（`1e7c7a9`／`36ba942`）

- Exact command使用既有PostgreSQL 16 image digest與`--pull never`，不接受mutable tag或隱性pull。
- Production connection只經Owner既有private `backup.env`傳入；argv與文件沒有DSN、password、host、port、database或user值。
- Repository以exact Windows path唯讀mount至`/workspace`且設定workdir，checksummed `\i` artifact可解析。
- `PGOPTIONS=-c default_transaction_read_only=on`提供connection-level read-only防線；SQL內仍保留transaction read-only、timeouts與rollback。
- Work獨立重跑targeted suites：24/24 passed；compileall與`git diff --check`通過。
- Fixed Docker version command因Docker Desktop daemon目前未啟動而無法實跑；命令以`--pull never`失敗且沒有下載或網路fallback。這是執行前本機prerequisite，不影響repository contract驗收；production SQL前必須先啟動Docker Desktop並取得exact PostgreSQL 16 version evidence。

結論：`accepted`，等待本branch唯一ready PR hosted gate。通過並merge後，Stage B可從Docker version preflight繼續；仍不得在Docker未啟動或version不符時連production。

## Stage B logging preflight production finding（2026-08-09）

- PR #86通過hosted gate並merge為`117fe1c`；固定Docker image實跑確認psql 16.4。
- Owner在production read-only session先執行無敏感輸入的logging preflight：duration、sample與pgAudit皆off，但`log_statement='none'`單一條件為false。進一步只回傳booleans的分類確認：`log_statement`屬`none/ddl/mod`安全集合、`log_duration=off`、transaction sample rate=0、`log_parameter_max_length_on_error=0`；全部為true。
- PostgreSQL 16官方規則下，`ddl`／`mod`不記錄本次pure SELECT；duration／transaction sampling均off，error parameter logging亦off。此組合對bound SELECT提供與任務相符的no-parameter-log boundary。
- Controlled SQL內嵌`statement_logging_safe`仍只接受`log_statement='none'`，因此若現在執行會把安全production組合誤判失敗。Work在任何allowlist／request ID prompt前停止並要求Owner`\q`；未執行inventory、未傳敏感參數。

結論：`changes_requested / codex`。請將preflight及SQL logging CTE共用同一個官方等價safe predicate：`log_statement IN ('none','ddl','mod')`、duration/sample off、`log_duration=off`、transaction sample rate=0、pgAudit none、on-error parameter length=0；保留unknown/failing cases與`log_statement=all` fail closed。更新checksum、runbook與offline tests，不得用session SET繞過。
