# TASK-085 Work review

## 第一輪驗收（2026-08-09）

### 已確認

- 實際驗收 branch `codex/phase-c-zero-admin-bootstrap`、implementation `77894b8a8e1d6e33f93e8e72288afb99c126bd16`；HANDOFF與branch一致，交回時工作樹乾淨。
- `bootstrap_zero_admin_member()`使用既有admin advisory lock，在transaction內確認target Member位於allowlist且active linked allowlisted admin為0；一般`approve_member()`仍保留原admin gate。
- Member link、Person active、legacy link、team_player、review thread與單一`identity_linked` null-actor audit已抽成共用transaction helper，未修改schema或`portal_access_level`。
- Codex本機僅執行3個static tests；11個PostgreSQL tests全部因無URL而skip。沒有production／env／Secret／gcloud／deploy操作。

### Blocking findings

1. **Pager-safe inventory未實作。** 新runbook只以文字要求pager-off，沒有在TASK-084 checksummed SQL或exact operator commands加入`\pset pager off`，也沒有真正psql16以超過一頁輸出證明不進pager且抵達`ROLLBACK`。本次production timeout根因仍可重現。
2. **必要併發契約未實作。** 沒有兩個獨立database sessions同時bootstrap的regression，且PostgreSQL 15／16均未實跑；不能用advisory-lock程式碼存在取代concurrency evidence。
3. **沒有可執行operator boundary。** `PHASE_C_ZERO_ADMIN_BOOTSTRAP.md`只描述直接呼叫repository method，沒有checksummed CLI／script、互動式輸入、private connection boundary、pre/post-check、dry-run或固定輸出schema。正式operator目前無安全可重現方式提供identity reference／Member ID／reason／request ID，也無法執行而不把值放進argv／transcript。
4. **Bootstrap retry驗證不足。** `_approve_member_in_transaction(... strict_bootstrap=True)`在既有request ID路徑只檢查action、identity與after-state Member ID，未要求`actor_person_id IS NULL`、target Person、exact before/after bootstrap shape及bootstrap reason/request boundary；同identity/member的普通admin approval audit可能被誤認成bootstrap retry。
5. Task要求的blocked/disabled、ignored/closed/redacted thread、qualification drift、failure rollback、錯誤identity/member、duplicate/ambiguous candidate與concurrency cases沒有直接測試證據。現有兩個integration tests不足以支持production mutation package。

結論：`changes_requested / codex`。補齊以上契約並以本機隔離PostgreSQL 15及16實跑；真正psql16 pager regression與operator CLI不得讀private env或production。若無法在0004與現有audit action內安全做到，交回Work，不得縮小驗收條件。

## 第二輪驗收（2026-08-09）

### 已解除項目

- 實際驗收review-correction implementation `b5234e45b055cfcd48a10edd2da302ee1bfca434`。
- Bootstrap retry現要求null actor、exact target Person、exact before/after shape及prefixed reason；普通admin approval audit不能充當bootstrap retry。
- Checksummed TASK-084 inventory已在`BEGIN`前固定`\pset pager off`，checksum及verifier同步更新。
- Codex回報已重用既有fictional legacy fixture，於隔離PG15/16執行bootstrap與two-session concurrency並通過；沒有production/private env操作，task containers已清除。

### Remaining blocking findings

1. **Operator artifact仍不存在。** Branch仍只有`IdentityLifecycleRepository.bootstrap_zero_admin_member()`與概念runbook；沒有task要求的checksummed executable CLI/script、固定redacted output schema、interactive input boundary、preflight/dry-run/execute/post-check modes。正式operator無法在不自行撰寫Python或把識別值放入不受控位置的情況下安全執行。
2. **Pager integration未跑exact artifact。** 新test只在generic psql script中`SELECT generate_series(1,200)`後印自訂`rollback-complete`；它沒有執行checksummed TASK-084 inventory、完整六欄metric set、bound parameters與artifact內的實際`ROLLBACK`。因此只能證明`\pset pager off`本身，不能證明reviewed operator path完整可執行。
3. **Failure/rollback matrix仍不足。** 新增的domain tests仍只有成功/retry、non-allowlisted/existing-admin及concurrency；沒有直接覆蓋blocked/disabled Person、ignored legacy row、closed/redacted thread、revoked qualification、wrong identity/member、ordinary-audit retry rejection，以及audit/qualification/thread failure injection後全transaction rollback。
4. **Codex report與實際證據矛盾。** `Limits`仍寫PG15/16、concurrency及psql16 evidence尚待執行，未列出exact local commands/container versions/results；交回訊息卻宣稱已通過。Report必須更新為可驗收且不含識別資料的真實證據。

### 新發現但不在本輪偷渡的production gap

- TASK-065 migration明確把全部People保留`portal_status='inactive'`，post-check要求noninactive count為0；目前Phase C principal resolver卻要求Person active。Production inventory的56 reliable linked LINE／56 active team_player因此仍可能全部無法登入。
- 這是Phase C linked-Person activation缺口，後續需獨立checksummed batch activation／audit／rollback package；不得在TASK-085 bootstrap中無聲批次修改其他55人。TASK-085只處理zero-admin bootstrap與其operator safety。

結論維持：`changes_requested / codex`。完成executable operator artifact、exact inventory psql regression、完整failure rollback matrix與一致report後再交回。

## 第三輪驗收（2026-08-09）

- 實際驗收 implementation `428d2099aae576bff73e3814b9ef68df581acfce`；checksummed operator只接受mode於argv，allowlist／identity／Member／reason／request ID／execute acknowledgement均以echo-disabled互動輸入，stdout固定為aggregate-only JSON。
- Operator具preflight／dry-run／execute、exact acknowledgement、zero-admin與target-ready pre-check、domain transaction及commit後admin/audit post-check；目前仍由`require_local_database_url`鎖定local-only，符合本task未授權production mutation的邊界。後續production execution package必須另行明確解除且由Owner批准。
- Work重跑offline suite：19 tests passed、1 opt-in按設計skipped；compileall、operator/inventory checksum verifier與`git diff --check`通過。
- Work以pinned PG16容器及repository local-only URL重跑完整`PhaseCLifecyclePostgresTests`：17/17 passed，涵蓋bootstrap、concurrency、operator、state drift、ordinary-audit拒絕與atomic rollback；容器已清除。
- Work另跑opt-in real psql16 exact checksummed TASK-084 inventory：1/1 passed，完整bind／metrics／artifact-owned pager-off／ROLLBACK path通過，容器已清除。Codex report另記錄PG15相同selected matrix 6/6 passed。
- 未連production、未讀private env／Secret、未執行gcloud／deploy／flags／traffic／IAM／Scheduler／通知，亦未處理56-Person activation。

結論：`accepted`。建立唯一ready PR並以hosted PostgreSQL 15／16 final gate補證；通過後squash merge。Production bootstrap及linked-Person activation仍須後續exact task與Owner批准。

## Hosted CI 驗收（2026-08-09）

- PR #89 的 PostgreSQL 15 與 16 jobs 均失敗；其他 required service jobs 通過。
- 兩個 PostgreSQL jobs 的共同失敗不是資料庫版本差異。完整 discovery 在新 bootstrap tests 後執行 `PhaseCReadinessPostgresTests.setUp()`，嘗試 downgrade 至 `0003_legacy_bigint_activity_game` 時，資料庫仍留有不符合舊版 `ck_access_audit_action` 的 Phase C audit rows。
- PostgreSQL 16 hosted log 顯示 182 tests、6 errors；第一個 traceback 為 `psycopg2.errors.CheckViolation: check constraint "ck_access_audit_action" ... is violated by some row`，發生於 `command.downgrade(..., "0003_legacy_bigint_activity_game")`。
- 本機 selected suites 通過不足以證明完整 discovery 的跨 test isolation；必須補 regression／cleanup，使 bootstrap tests 與 readiness downgrade tests 可在同一 hosted suite 安全接續。

結論：`changes_requested`。PR #89 不得合併；Codex 僅修正 test isolation／fixture cleanup，不能放寬 migration constraints、跳過 readiness tests，亦不得納入另案的 56-Person activation。

## Hosted CI 補正複驗（2026-08-09）

- 實際查驗 implementation `e018e8297a03644ea14734e9154aec582e611ce2`；變更只清理 readiness test database 的 `access_audit` fixture residue，未修改 migration 或正式 constraint。
- 新增 regression 明確建立不相容的 Phase C audit residue，再證明 reset 可安全回到 0003 且 audit fixture 為空。
- Work 本機重跑 readiness module：15 tests，8 passed、7 個 PostgreSQL tests 因未設定隔離 URL 按設計 skipped；compileall、`git diff --check` 與工作樹檢查通過。
- GitHub Actions run `31308455551` 全部通過：PostgreSQL 15、PostgreSQL 16、所有服務 jobs 與 CI final gate 均為 success。

最終結論：`accepted`。PR #89 可 squash merge。Production bootstrap 與 56 linked-Person activation仍未授權，必須由後續 exact tasks 分開處理。
