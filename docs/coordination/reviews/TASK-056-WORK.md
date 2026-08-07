# TASK-056 Work prerequisite 驗收

## 結論

Docker archive-inspection prerequisite `accepted`。固定 image、no-pull/network-none/read-only sandbox、
read-only archive-parent mount 與 limited `pg_restore --list/--version` backend 已通過 code review、18 項
tests，以及對 real local fake custom archive 的 `create`／`verify` 實跑。

TASK-056 production logical backup 本體尚未執行或結案。Production dump 必須等 prerequisite push／PR／
Python 3.10 CI／merge 後，由 Work 重新鎖定 merged commit 與 exact command，再取得 Owner 明確批准。

## 查驗基準

- Branch：`codex/task056-production-backup-authorization`
- Task planning commits：`4d4ee40`、`dd4c104`
- Docker backend implementation：`ea241f7`
- Codex report／handoff：`6d238d013959466fa6662470dab60b6f30910c87`
- Working tree clean。

## Work boundary review

- Default `host` backend behavior保持相容；`docker` 需 explicit CLI option。
- `preflight --backend docker` 不 resolve 或啟動 Docker。
- Image 固定為既有 image ID，且 `--pull never`。
- Container 使用 `--rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges`。
- 只 mount 已驗證 archive parent 到 `/backup`，mode `readonly`；repository、direct home、symlink/reparse、
  comma-delimited mount source 皆拒絕。
- 只接受 configured archive 的 `pg_restore --list` 或 `pg_restore --version`；任意 archive、option、backend、
  DB/network command 在 subprocess 前拒絕。
- 不傳 env-file、container `-e`、credential、Docker socket、repository/home mount 或 host secrets。
- Subprocess 使用 argument list、restricted environment、timeout、capture、`shell=False`；錯誤不回顯 output
  或 path。
- 未增加 `pg_dump`、restore、SQL、connection、network、delete 或 overwrite 能力。

## Work 實際驗證

- Bundled Python 3.12 focused suite：18/18 passed。
- Compile：passed。
- `git diff --check`：passed。
- Real local fake Docker backend rehearsal：
  - 從 stopped task-owned container 複製既有 fake custom archive到全新 system temp directory；
  - `create --backend docker`：passed；
  - `verify --backend docker`：passed；
  - 精確 task temp directory 驗證後已刪除；
  - production destination `C:\NTUBTOB-secure-backup` 未寫入，仍應保持 empty；
  - credential env-file 未開啟或傳給 rehearsal。

## 尚待證據／下一閘門

- Python 3.10 hosted CI 與 formatter evidence 待 PR。
- 尚未讀 env-file、連 Supabase、執行 production dump 或建立 production archive。
- Owner 可授權 prerequisite branch push、Draft PR、CI 與 squash merge；該授權不包含 production backup。
- Merge 後 Work 必須重新 preflight exact merged commit、destination、image 與 paths，才可提出最終 production
  command 供 Owner 另行批准。

## 安全聲明

未讀 `.env.yaml`／env-file／DSN／secret，未連 remote／production，未執行 production dump、restore、SQL、
migration、schema/cloud change 或 deployment。

## TOC identifier compatibility correction 驗收

結論：`accepted`，可進入 push／PR／Python 3.10 CI 閘門。

- 驗收 branch：`codex/task056-toc-identifier-compatibility`
- 實作 commit：`50902dd7df86741f30e9d4632ed2af9d7332037b`
- `line_notify_tokens` 等十張 TASK-049 catalog 既有表名均可通過假 TOC 驗證。
- `password`、`secret`、`token` 僅在 ASCII identifier 邊界完整出現時命中；獨立詞與
  `token-value` 仍會 fail closed，URL／DSN、SQL、foreign schema 與任意 TOC 防線未移除。
- Visual Studio Python 3.9 focused suite：19/19 passed。
- Python compile：passed；`git diff --check`：passed；working tree clean。
- 本機已登錄的 Python 3.10 WindowsApps executable 無法啟動，故 Python 3.10 證據必須由 hosted CI 補足。
- 驗收期間未讀 production archive／env-file，未啟動 Docker、連線 Supabase、重跑 dump、建立 sidecar、
  restore、執行 SQL／migration 或部署。

此接受不授權重新檢查 retained production archive。修正 merge 後仍須由 Owner 另行批准只對既有 archive
執行 verifier `create`／`verify`；不得重跑 production dump。

## Production logical-backup evidence closeout

結論：`accepted`。Owner 批准後，Work 在 merged commit
`d8ec8b175ff3f7106fcad978e93970714afabdca` 對既有 retained archive 執行一次 Docker verifier
`create` 與一次 `verify`，兩者均通過。

- Archive basename：`portal-data-backup-20260807T063211Z.dump`
- Archive bytes：`56,903`
- SHA-256：`a339a4ccd087a309468308e3912a08e5b661924447c93f57168d6e58b45f0f43`
- Evidence created UTC：`2026-08-07T07:12:00.581462Z`
- `pg_restore` client major：`16`
- Validation：custom format、`ntubtob` schema scope、listing verified。
- Adjacent `.manifest.json` 與 `.sha256` sidecars 已建立；隨後獨立 verify 通過。

執行前的 `preflight` 因 archive 已存在而依設計拒絕；這是 pre-dump gate，不適用於 retained archive，且未
造成寫入。其後只執行 Owner 明確批准的 evidence create／verify。未讀 credential env-file、未連 Supabase、
未重跑 dump、未 restore、未執行 SQL／migration、未刪除／移動／上傳 archive，repository 保持乾淨。
