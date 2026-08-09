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

## 第二輪驗收（2026-08-09）

- 驗收 correction implementation `d931d286d6ed497e20d92ba0962d6146ea126ba7`；execute 已改用獨立 none/ddl-only write gate，且發生在request ID生成與domain DML前。真實PG regression涵蓋`mod`時audit零變化。
- No-disclosure launcher已鎖定artifact、account/project/service/region、單一allowlist metadata projection、private PG env parser、五階段sequence與finally cleanup；敏感值不在child argv或固定錯誤輸出。
- Work重跑launcher/operator suites 19/19 passed；compileall、`git diff --check`與工作樹檢查通過。

### Remaining blocker

Runbook的exact production命令`py -3.10 tools/launch_production_zero_admin_bootstrap.py`在本機不可執行。`py -0p`雖列出Microsoft Store Python 3.10 alias，但實際`py -3.10 -c ...`回傳`Unable to create process`，因此目前launcher無法到達任何自身guard。可用的bundled runtime為Python 3.12.13，且SQLAlchemy 2.0.23、alembic 1.13.1、psycopg2-binary 2.9.9均精確符合launcher鎖定版本。

請將launcher與runbook改為實際存在且可查證的exact runtime boundary：可鎖定目前bundled Python 3.12.13 executable/path/version與相依版本，並由hosted Python 3.10保留相容性證據；或提供另一個已實際啟動成功的pinned Python 3.10 runtime。必須新增real subprocess smoke，證明exact documented command能從repository root啟動launcher並在production access前因缺少／假approved commit安全停止；不得要求Owner安裝軟體、下載依賴或手動修復Windows alias。

結論仍為：`changes_requested / codex`。只修operator runtime可執行性與契約測試；不得呼叫gcloud、讀private env、連production或執行DML。

## 第三輪驗收（2026-08-10）

- 驗收 runtime implementation `8cbadb7e95b131d1c96ead9920dde3d34048c2a5`；launcher與runbook已鎖定實際存在的bundled Python 3.12.13 executable及精確dependency版本，hosted Python 3.10仍作相容性證據。
- Work依文件exact executable從repository root執行launcher，注入假approved commit；process只輸出固定`TASK-086 production launcher stopped`並以exit 1停止，未到達gcloud、private env或production access。
- Work重跑launcher/operator suites 20/20 passed；compileall、`git diff --check`與工作樹檢查通過。先前PG15/16完整190項證據維持有效，因本輪只改launcher runtime/import boundary及其tests。
- 本次複驗未讀private env／Secret、未呼叫gcloud、未連production、未執行DML／deployment／cloud mutation或56-Person activation。

結論：`accepted`。建立唯一ready PR並以hosted Python 3.10、PostgreSQL 15／16與final gate補證；全部通過且branch不再變更後可squash merge，再依TASK-086已授權範圍執行production五階段launcher。
