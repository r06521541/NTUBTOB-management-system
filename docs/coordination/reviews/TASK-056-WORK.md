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
