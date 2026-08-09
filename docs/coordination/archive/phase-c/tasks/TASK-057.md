# TASK-057：建立 fail-closed 的隔離 restore rehearsal 工具

## 任務目標

建立可離線驗證、預設不執行的 Docker restore rehearsal wrapper，使已驗證的 PostgreSQL custom archive
未來只能還原到一次性、無網路、無 published port、無 persistent volume 的本機隔離資料庫。先以明顯虛構
archive 完成端到端 rehearsal；本任務不讀取或還原 production archive。

## 背景與已確認事實

- TASK-056 已建立並驗證 production `ntubtob` schema archive、manifest 與 checksum。
- 合併基準為 `d8ec8b175ff3f7106fcad978e93970714afabdca`；TASK-056 closeout commit 為 `e2b75a8`。
- 現有 `portal_data_logical_backup.py` 只允許 `pg_restore --list`／`--version`，刻意沒有 restore 能力。
- Runbook 要求 restore 僅能進入全新 isolated non-production database，且禁止 production/shared target、
  `--clean`、`--create`、drop、overwrite 與 production row-content evidence。
- Docker Desktop 已有固定 PostgreSQL 16.4 Alpine image ID：
  `sha256:89ec47deeeddac28eb60b5672a456c54213ff4528f8752fda7f7c2a0e4ead36a`。

## 工作範圍

1. 新增獨立 restore rehearsal wrapper，不擴張現有 read-only backup verifier 的 command allowlist。
2. Wrapper 必須提供明確 `preflight` 與 `execute` 分離；預設／缺少 execute acknowledgement 時不得啟動 Docker。
3. Execute 前重新呼叫或等價使用既有 verifier，要求 archive、manifest、checksum 全部通過且 basename 對應。
4. Docker target 必須：
   - 使用上述固定 image ID與 `--pull never`；
   - `--network none`、不得 `-p/--publish`；
   - 不使用 named/anonymous persistent volume；database data directory 使用 bounded tmpfs；
   - archive parent 僅 read-only bind mount；不得 mount repository、home、env-file、Docker socket；
   - 使用精確 task-owned container name，拒絕覆蓋／接管既有 container；
   - 不接收 production DSN、PGHOST、credential env-file、Secret 或 remote database option。
5. 只允許等價 restore contract：
   `pg_restore --exit-on-error --single-transaction --no-owner --no-privileges`，目的地只能是 container 內
   新建的固定 rehearsal database；禁止 `--clean`、`--create`、`--if-exists`、jobs、schema remap 或任意 option。
6. Restore 後以固定 catalog queries 產生 sanitized pass/fail evidence：
   - `ntubtob` schema 與十張 legacy tables 存在；
   - columns/types/nullability/default/identity、PK/FK/check/index/trigger、RLS enabled/forced 與 policy presence
     可和 TASK-049 sanitized catalog 比較；
   - 只輸出 generic categories／boolean，不輸出 row values、LINE IDs、member names、connection identity、
     exact production row counts或完整 catalog/TOC。
7. 可驗證 aggregate row-count consistency，但對 repository/report 只能記錄「全部一致」或失敗類別；不得
   commit 或列印逐表 production counts。
8. 成功或失敗皆 bounded cleanup 精確 task-owned container；確認沒有 persistent volume、published port 或
   running container 殘留。若 cleanup 無法證明，fail closed 並回報 sanitized container reference。
9. 新增離線 tests，mock subprocess 驗證 exact argv、安全 flags、狀態機、timeout/nonzero、輸出抑制、
   pre-existing container、cleanup failure 與禁止參數；另以明顯虛構 custom archive 做真實本機 Docker rehearsal。
10. 更新 logical-backup runbook，明確記錄 wrapper、操作順序、stop conditions 與 production archive 的另行批准閘門。

## 非目標

- 不讀取、mount、restore 或 inspect `portal-data-backup-20260807T063211Z.dump` 及其 sidecars。
- 不讀 credential env-file，不連 Supabase／production／staging/shared database。
- 不修改 production schema、資料、RLS、grant、role、Secret、IAM、Cloud Run/Functions/Scheduler。
- 不執行 Phase A migration、Member backfill、application rollout 或任何通知。
- 不新增正式 migration framework、不修改 shared models／schema migration SQL。
- 不 push、建立 PR、merge、部署；除非 Owner 另行批准 PR 工作包。

## 設計與安全決策

- Production-derived data 即使位於 local 仍視為敏感；正式 rehearsal 必須使用 ephemeral tmpfs，不能以方便
  為由留下 Docker volume。
- Container 不暴露 TCP port且 network namespace 為 none；所有 restore/catalog checks 透過受限的
  `docker exec` argv 在 container 內進行。
- Wrapper 不接受任意 SQL。Catalog queries 必須固定在 source 中並接受 code review；stderr/stdout 需轉成
  不含資料、path、Docker output或SQL result的安全錯誤分類。
- cleanup 是任務成功條件，不以 subprocess exit zero 取代殘留檢查。
- 真實 archive rehearsal 必須等待此工具經 Work review、Python 3.10 CI 與 merge，再由 Owner 批准 exact
  commit、archive set、時間窗與 cleanup boundary。

## 驗收條件

- 缺少 explicit execute acknowledgement 時，Docker invocation 為零。
- 所有 Docker/pg_restore/psql argv 均為固定 allowlist；tests 證明 remote target、port、volume、任意 SQL、
  destructive restore flags 與 alternative image 皆在 subprocess 前拒絕。
- 假 archive 的真實 Docker restore 成功，fixed sanitized catalog checks 通過，且結束後無 container／volume／
  port 殘留。
- Injected restore/catalog/timeout/cleanup failures 均 fail closed，不顯示 row data、archive listing、path、
  credentials或 raw subprocess output。
- Python 3.10 相容；focused tests、compile、formatter、`git diff --check` 通過。
- 文件清楚說明：工具完成不等於授權正式 archive restore，也不等於 Phase A migration readiness。

## 驗證命令

Codex 應依最終檔名補上並執行：

```powershell
python -m unittest tests.portal_data.test_restore_rehearsal -v
python -m py_compile tools/portal_data_restore_rehearsal.py tests/portal_data/test_restore_rehearsal.py
python -m black --check tools/portal_data_restore_rehearsal.py tests/portal_data/test_restore_rehearsal.py
python -m isort --check-only tools/portal_data_restore_rehearsal.py tests/portal_data/test_restore_rehearsal.py
git diff --check
git status --short
```

若執行真實假資料 Docker rehearsal，報告只能記錄 image ID、pass/fail、generic object categories 與 cleanup
結果，不得提交 archive、database files、TOC、row contents或 exact row counts。

## 已知風險與待驗證假設

- PostgreSQL Alpine image 在 `--network none`、tmpfs 與權限最小化組合下的 initdb/runtime requirements 尚待
  真實假資料 rehearsal 確認；不得為通過而改成 published port 或 persistent volume。
- Windows Docker bind-mount path 與 tmpfs options 需真實驗證。
- TASK-049 catalog 是 sanitized snapshot；正式 archive rehearsal 前仍須確認比較規則沒有把合法 drift 靜默接受。
- Logical backup 不含 ownership/ACL，故 rehearsal 不能證明 Supabase runtime grants、API exposure 或 provider
  disaster recovery。

## 需要 Owner 決策

- 本輪 Codex 僅實作／測試假資料 wrapper，不需要 production data operation 授權。
- 工具通過 review／CI／merge 後，Owner 必須另行決定是否批准正式 archive 的一次性 isolated restore rehearsal。

## Base commit

`e2b75a8`
