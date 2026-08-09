# TASK-086 Work review

## 第一輪驗收（2026-08-09）

- 驗收 branch `codex/phase-c-production-bootstrap`，implementation `74ce7b632a35fed7a105655e025d602fa3b165b1`，handoff HEAD `5059ab8de0c3ecbc5c7baf8adf60131ba03207b0`；交回時工作樹乾淨。
- 實際 diff 確認 TASK-085 local-only operator 未被放寬；新增 production artifact 有 checksum、固定 redacted output、read-only discovery、唯一候選、內生 request ID、domain transaction、aggregate/relationship post-check與same-request retry。
- Work 重跑兩組 offline operator suites：11/11 passed；compileall、`git diff --check`與工作樹檢查通過。Codex report記錄隔離PG15/16 hosted-equivalent full discovery各189/189 passed。

## Blocking findings

1. **DML logging gate不足。** `_logging_safe()`沿用read-only inventory predicate並接受`log_statement IN ('none','ddl','mod')`，但沒有檢查`log_parameter_max_length`。`mod`會涵蓋本operator的DML；只把`log_parameter_max_length_on_error`設為0不能證明一般成功statement的bind parameters不會被provider log保存。Execute必須要求`log_statement IN ('none','ddl')`，或在允許`mod`時同時以可證明的server setting禁止一般parameter payload；unknown/unavailable必須fail closed。Discovery/preflight仍可使用已核准的read-only predicate，但不得把它誤當write-safe predicate。新增離線與PG regression，證明`mod`+未封鎖一般parameter logging在任何mutation前停止。
2. **Private environment channel尚不可執行。** Runbook只假設process已有`PORTAL_DATA_DATABASE_URL`與`WEB_PORTAL_ADMIN_MEMBER_IDS`。既有Owner-approved private `C:\Users\USER\.ntubtob-private\backup.env`提供標準`PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD`，不是SQLAlchemy DSN；allowlist存在Web Portal production runtime metadata，且不得讀出、顯示或放進argv。請提供checksummed或contract-tested exact launcher boundary：使用private env-file path但不讀／echo內容，安全取得精確Web Portal allowlist metadata到process environment且不輸出值、不放argv，執行後清除process value；不得查詢完整runtime config、Secret或其他env values。若無法安全組合這兩個來源，必須明確stop並交回Owner親自輸入，不能把未準備的environment當成可執行runbook。
3. **Production command與cleanup證據不足。** Exact operator path需鎖定merged artifact/checksum、Python/shared dependencies、repository root、private env path、account/project/service/region guard，以及discovery→preflight→dry-run→execute→post-check順序。任何temporary file/process environment必須有finally cleanup與no-output contract；不得在PowerShell transcript、Docker argv、process list或GitHub log留下allowlist/DB credential。

結論：`changes_requested / codex`。僅補write-safe logging與可重現private launcher；不得連production、讀private env/Secret、執行DML、處理56-Person activation或擴張至deployment/cloud mutation。
