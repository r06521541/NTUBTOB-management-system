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
