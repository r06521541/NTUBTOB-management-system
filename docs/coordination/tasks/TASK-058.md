# TASK-058：一次性 production archive isolated restore rehearsal

## 任務目標

在本機 Docker Desktop 中，使用已合併、CI 通過的 TASK-057 wrapper，將 TASK-056 的 retained production
archive 還原到無網路、無 published port、無 persistent volume 的一次性 tmpfs PostgreSQL database，完成
sanitized catalog checks、二次 archive verification 與 ownership-guarded cleanup。

本文件是精確執行包；建立文件本身不授權讀取、mount 或 restore production archive。

## 已確認執行基準

- Repository／tool commit：`1c07871feb8f64f59fd4909845476771caf2f346`。
- PR #61 Python 3.10 CI run `31160495693`：passed。
- Fixed Docker image ID：
  `sha256:89ec47deeeddac28eb60b5672a456c54213ff4528f8752fda7f7c2a0e4ead36a`。
- Artifact directory：Owner 先前指定的 repository 外加密位置 `C:\NTUBTOB-secure-backup`。
- Exact artifact set：
  - `portal-data-backup-20260807T063211Z.dump`
  - `portal-data-backup-20260807T063211Z.manifest.json`
  - `portal-data-backup-20260807T063211Z.sha256`
- TASK-056 sanitized evidence：archive 56,903 bytes、SHA-256
  `a339a4ccd087a309468308e3912a08e5b661924447c93f57168d6e58b45f0f43`、client major 16、custom format、
  `ntubtob` schema scope與 listing verified。
- TASK-057 fake-data rehearsal、32/32 Work tests、Python 3.10 hosted CI 與 cleanup ownership correction均通過。

## Owner 批准後的精確操作

Work 只可在 repository clean 且 HEAD 為上述 exact commit 時：

1. 唯讀確認三個 artifact 是 adjacent regular/non-reparse files、basename/size/checksum contract 未漂移；確認
   fixed Docker image 存在且沒有 TASK-057 container／labeled volume 殘留。
2. 執行 wrapper path-only `preflight`；此步不得啟動 Docker。
3. 執行一次：

```powershell
& 'C:\Program Files (x86)\Microsoft Visual Studio\Shared\Python39_64\python.exe' -m tools.portal_data_restore_rehearsal execute `
  'C:\NTUBTOB-secure-backup\portal-data-backup-20260807T063211Z.dump' `
  'C:\NTUBTOB-secure-backup\portal-data-backup-20260807T063211Z.manifest.json' `
  'C:\NTUBTOB-secure-backup\portal-data-backup-20260807T063211Z.sha256' `
  --acknowledge TASK-057-EPHEMERAL-LOCAL-RESTORE
```

4. Wrapper 固定執行：restore 前 artifact verify、ephemeral Docker restore、13 個 catalog boolean categories、
   restore 後 artifact verify、ownership-guarded cleanup。
5. 唯讀確認沒有 `ntubtob-task057-*` container、TASK-057 labeled volume 或 published port 殘留。
6. Repository 只記錄 generic pass/fail categories、cleanup 結果、merged commit與既有 sanitized archive evidence；
   不記錄 row values、TOC、SQL output、container logs、exact restored row counts或個人識別資料。

## Isolation 與資料邊界

- Docker 使用 fixed image、`--pull never`、`--network none`、無 `-p/--publish`、無 persistent volume。
- Database data、runtime socket與 temp files 只存在 bounded tmpfs；container cleanup 後不保留 restored database。
- Artifact parent 僅 read-only mount；archive、manifest、checksum 不得修改、刪除、移動、複製或上傳。
- 不讀 credential env-file，不使用 DSN／PGHOST，不連 Supabase、production、staging或任何 remote database。
- Fixed catalog SQL 只回傳 boolean categories，不允許 ad-hoc SQL、shell、psql或 Docker exec。
- Cleanup 必須先驗證 exact TASK-057 label、fixed image ID與 immutable container ID；ownership 不明時不得刪除。

## Stop conditions

- Git HEAD／working tree、artifact basename/type/size/checksum、image ID 或 wrapper contract 漂移。
- 任何 artifact sidecar mismatch、preflight/verify/restore/catalog failure或 raw subprocess output意外曝光。
- Docker 出現既有／ambiguous同名 container、network/port/volume、ownership mismatch或 cleanup 無法證明。
- Host 發生 production incident、磁碟／Docker狀態不明，或執行期間有人要求 migration/deployment/backfill。

Stop 後不得重跑、修改 options、手動進入 container、查詢 rows或刪除未知資源。若 wrapper 證明是 exact
TASK-057-owned container 才可依既有 cleanup contract 移除；否則保留 sanitized reference 並請 Owner 決策。

## 明確未授權

- 不連 production DB，不重跑 `pg_dump`，不讀 credential env-file。
- 不 restore 至 production／Supabase／shared database，不建立 persistent local clone。
- 不執行 Phase A migration、DDL、DML、baseline stamp、backfill、RLS/grant/role或 application rollout。
- 不部署、發送 LINE／Discord、修改 Secret／IAM／Scheduler／Cloud Run／Functions。
- 不 push、建立 PR、merge；rehearsal evidence 文件只建立 local commit，後續 Git 操作另行決定。
- 不刪除、移動、上傳或同步 archive／manifest／checksum。

## 能證明與不能證明的事項

成功可證明：

- retained archive 可被 PostgreSQL 16 client 原子 restore 至隔離 database；
- 十張 legacy table 的既定 schema/catalog contract、RLS flags/policy presence與 table-data scans通過；
- restore 前後 archive evidence一致，且 restored data沒有 persistent Docker residue。

成功仍不能證明：

- dump 時點與目前 production 的 row counts相同；
- Supabase ownership/ACL、runtime grants、API exposure、PITR/provider recovery；
- Phase A migration SQL 可安全執行或應立即執行。

Phase A 前仍須以另行批准的 production read-only baseline確認當下 catalog與 aggregate counts，不能用
TASK-049 前一日快照或本次 restored counts取代。

## 完成定義

- Owner 批准本文件列出的 exact commit、artifact set、一次 execute與 cleanup boundary。
- Preflight、restore前 verify、restore、13 catalog categories、restore後 verify全部成功。
- Container／volume／port residue為零；archive set未變更。
- Sanitized Work evidence與 PROJECT_STATE/HANDOFF已更新；未執行任何明確未授權事項。

## Base commit

`1c07871feb8f64f59fd4909845476771caf2f346`
