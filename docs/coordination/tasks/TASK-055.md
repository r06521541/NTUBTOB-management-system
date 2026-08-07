# TASK-055：準備 production logical backup 與 restore-readiness 工作包

## 背景

TASK-054 確認 production 目前沒有 provider backup、PITR 或涵蓋 migration／驗證視窗的 retention；
Owner 有 restore authority，`ntubtob` 不暴露於 Data API，migration 預定走 direct connection。Phase A
migration 因缺少可用 recovery artifact 而維持 blocked。

本任務只建立並離線驗證安全的 logical-backup 工作包，不連 Supabase、不讀 DSN、不產生 production
backup。實際執行 `pg_dump`、處理 production data 或 restore 仍需 Owner 對精確來源、命令、時間與
輸出位置另行批准。

## 目標

- 定義只涵蓋 `ntubtob` schema 的 portable PostgreSQL custom-format logical backup。
- 讓 operator 可在不把 secret 放進 command line、log 或 Git 的前提下執行、驗證與保存 archive。
- 提供 repository-only verifier，檢查輸出路徑、archive metadata、checksum 與 sanitized manifest，
  但不得內建或接受 remote connection／production DSN。
- 以 isolated local fake PostgreSQL 證明 dump、list、restore 與資料／schema fidelity 流程可行。

## 實作範圍

### 1. Backup／recovery runbook

新增 runbook，至少包含：

- preflight：核准 commit、maintenance window、PostgreSQL client/server major compatibility、direct
  reachability 待人工確認、足夠 disk、加密且非同步雲端的 repository 外保存位置；
- credential boundary：密碼只由 operator 的暫時 process environment 或受限 password file 提供；
  不得出現在 argv、shell history、URL、manifest、checksum、log 或 repository；
- reviewed `pg_dump` contract：custom format、只含 `ntubtob`、portable ownership/ACL 邊界、bounded
  lock wait、無 overwrite、無 stdout archive；
- validation：`pg_restore --list`、SHA-256、archive size/non-empty、sanitized manifest、第二次驗證
  checksum；
- restore-readiness：只允許還原到 isolated non-production database；禁止 drop／clean／restore 到
  production，並列出 schema、row-count、sequence、constraint 與 RLS fidelity checks；
- retention：保存到 Phase A 驗證完成及 Owner 確認後，再以另行批准的安全刪除處理；
- stop conditions、失敗清理、ambiguous output、client version mismatch 與 credential exposure response。

Runbook 可提供精確 command template，但不得含真實 host、project ref、role、password、DSN 或可由本
任務直接執行 production 的 wrapper。

### 2. Offline artifact verifier

新增 Python 3.10-compatible 工具，只接受 local archive／manifest／checksum 路徑，且：

- fail closed 拒絕 archive 或輸出位於 repository、符號連結／reparse point、非 regular file、空檔、
  已存在的預定輸出、路徑 traversal 或不符合固定副檔名；
- 呼叫 local `pg_restore --list` 時使用 argument list、timeout、captured output，錯誤訊息不回顯環境、
  command line 或 archive listing；
- 驗證 custom-format archive 可列出，並拒絕 listing 中出現 `ntubtob` 以外 application schemas；
- 產生／驗證 SHA-256 與 sanitized manifest。Manifest 只允許格式版本、generic purpose、UTC timestamp、
  basename、byte size、SHA-256、client major 與驗證結果；禁止任意額外欄位；
- 不接受 connection string、host、port、user、password、database、project ref 或 SQL；不連網、不執行
  `pg_dump`／`pg_restore` restore、不刪檔、不覆寫既有檔案；
- error／stdout 不洩漏 environment values 或 archive listing。

工具名稱與 CLI 可由 Codex依相鄰風格決定，但行為與安全邊界必須有測試。

### 3. Offline tests 與 local rehearsal

- 單元測試使用明顯虛構 path／listing／manifest，mock subprocess 與 clock，不需 PostgreSQL 或網路。
- 覆蓋合法 artifact、repo 內路徑、symlink/reparse、empty file、checksum mismatch、manifest 額外欄位、
  sensitive-looking value、timeout、non-zero exit、foreign schema 與 listing 注入。
- 若 Docker／local PostgreSQL 可用，可對既有 isolated fake baseline 實際執行 local-only dump/list/restore，
  驗證 schema objects、fake row counts、sequence、constraints 與 RLS flags；不得為此安裝軟體、連 remote
  database 或使用 production data。
- local rehearsal 產物必須在 repository 外暫存目錄，完成後只清理本任務明確建立且已驗證的暫存目標。

### 4. 文件同步

- 更新 production migration runbook 與 evidence template，引用 logical backup artifact、checksum、manifest
  與 isolated restore validation gate。
- Codex report 明確列出 offline/local-only 證據與未執行項目。

## 非目標與禁止事項

- 不讀取 `envs/**/.env.yaml`、service `.env.yaml`、DSN、secret、host、project ref 或 role name。
- 不連 Supabase／production DB，不執行 production `pg_dump`、SQL、API、restore 或 migration。
- 不建立、複製、檢視或提交任何 production data archive。
- 不修改 backup/PITR、RLS、grant、role、schema、Cloud Run、Function、Scheduler、Secret 或 IAM。
- 不建立 production restore／drop／clean 自動化，不自動刪除 backup。
- 不 push、建立 PR、merge 或部署。
- 不同時實作 maintenance mode；該項留給下一個獨立任務。

## 驗收條件

1. Runbook 能讓 reviewer 清楚看到 credential、archive、驗證、保存、restore 與停止邊界。
2. Offline verifier 無 remote connection 能力，且無法將 archive／manifest 寫入 repository 或覆寫既有檔案。
3. 固定 manifest 不含 identity／connection metadata，checksum 與 archive listing 驗證 fail closed。
4. 單元測試覆蓋成功與重要失敗路徑，Python 3.10 CI、compile、Black、isort、`git diff --check` 通過。
5. Local fake rehearsal 若環境可用則通過；若不可用，report 必須列出限制，不能宣稱 restore 已驗證。
6. Phase A migration 與 production backup 在 Owner 後續明確批准前仍 blocked。

## 建議驗證命令

```powershell
py -3.10 -m unittest <TASK-055 offline tests> -v
py -3.10 -m compileall -q tools tests/portal_data
py -3.10 -m black --check <TASK-055 Python files>
py -3.10 -m isort --profile black --check-only <TASK-055 Python files>
git diff --check
git status --short
```

## 預期文件／程式

- `docs/operations/data/PORTAL_DATA_LOGICAL_BACKUP_RUNBOOK.md`
- repository-only artifact verifier 與 tests
- `docs/operations/data/PORTAL_DATA_PRODUCTION_MIGRATION_RUNBOOK.md`
- `docs/operations/data/PORTAL_DATA_MIGRATION_EVIDENCE_TEMPLATE.md`
- `docs/coordination/reports/TASK-055-CODEX.md`

## 建議 commit

`security(data): prepare logical backup recovery controls`

Commit body/footer 加上 `Refs TASK-055`。

## Base commit

`fd647c01da9d7cc968a28e0b7229e1993b92abe1`
