# TASK-062：建立 Phase A deterministic pre/post-check evidence gate

## 任務目標

在production Phase A migration前，建立固定、唯讀、去識別化且可離線驗證的pre/post-check SQL與結果contract，
並在local fake PostgreSQL完整演練baseline → migration → post-check。消除正式執行後依賴ad-hoc SQL的缺口。

## 背景

- TASK-060 migration artifact已merge為`0d54a4c017dc66dc0d25b037e93f09e1e62a6a12`，SHA-256為
  `81fa1ba1a2d2d856d4b4393cbdfbc663d6c19759f758f36b08e76e39a964636a`。
- TASK-061新鮮baseline通過：10張legacy tables、三個fingerprints match、無marker／portal tables、legacy
  RLS 10/10，migration-owner boundary未漂移。
- Runbook要求驗證revision、objects、constraints、indexes、function/triggers、nullable empty `members.person_id`、
  legacy counts、new-table emptiness、13-table RLS與zero policies/grant drift，但目前沒有exact post-check artifact。

## 工作範圍

1. 新增固定read-only pre/post-check SQL：
   - 單一`BEGIN TRANSACTION READ ONLY`與`ROLLBACK`，設定bounded timeouts；
   - 只查`pg_catalog`／`information_schema`及固定`ntubtob` allowlist；
   - 不輸出row values、identity、role/account、host、DSN、policy expressions或exact object definitions；
   - 輸出固定ordered metrics與six-column contract，可由Supabase SQL Editor匯出單一CSV。
2. Pre-check必須證明TASK-061 gate仍成立，並產生可在repository外比較的legacy aggregate invariants。
3. Post-check必須fail closed驗證：
   - revision exactly `0003_legacy_bigint_activity_game`；
   - exact 13 new tables及預期columns／PK-FK／constraints／indexes；
   - append-only function/triggers存在；
   - `members.person_id` nullable、unique/FK且non-null count為0；
   - new application tables row count均為0；
   - legacy aggregate invariants與pre-check相符；
   - 13張新表RLS enabled、not forced、zero policies；
   - 沒有artifact外新增的grant/revoke可見漂移。
4. 建立offline CSV validator、明顯虛構fixtures與mutation tests；未知／缺少／重複metric或敏感輸出fail closed。
5. 在local fake PostgreSQL演練pre-check → exact merged migration artifact → post-check；另測未migration、partial／
   drifted schema、unexpected rows、RLS/policy drift與legacy invariant drift皆被拒絕。
6. 更新production runbook與evidence template，明確固定Owner執行順序、stop conditions與repository外CSV處理。

## 非目標

- 不連Supabase／production，不讀Owner CSV／archive／credential或env。
- 不執行production SQL、migration、DDL/DML、stamp、backfill或application rollout。
- 不修改已merge migration artifact、migration revisions、models、runtime services、RLS policies或grants。
- 不部署、不通知、不修改Secret／IAM／Scheduler／cloud resources。
- 不建立production execution授權；TASK-062完成後仍須Work另建exact execution package並由Owner批准。

## 驗收條件

- SQL與CSV contract有strict allowlist/checksum或等價deterministic verifier。
- Python 3.10相容；Black/isort、compile與受影響tests通過。
- Local clean success及所有fail-closed mutation/rehearsal cases通過。
- SQL不含mutation、role operations、remote/credential text或raw identity輸出。
- `git diff --check`通過，task-ownedcontainer/network清除，既有local fake volume可保留。

## 驗證命令

```powershell
python -m unittest discover -s tests/portal_data -v
python -m compileall -q tools tests/portal_data
python -m black --check tools tests/portal_data
python -m isort --profile black --check-only tools tests/portal_data
docker compose -f docker-compose.portal-data.yml config
git diff --check
git status --short
```

## Base commit

`f138e6e`
