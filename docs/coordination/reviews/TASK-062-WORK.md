# TASK-062 Work review

## 結論

`accepted`。Work查驗實際diff、commits、SQL、validator、mutation tests、Draft PR #63與hosted CI，並獨立在
repository-defined PostgreSQL 16 fake database重跑完整106項portal-data tests。第一輪finding已補正：pre/post
現在都保護legacy fingerprints與generic access/grant boundary，post亦拒絕portal非Owner direct/default grants。
這不授權production migration。

## 驗收基準

- Branch：`codex/task062-deterministic-postchecks`
- Final code commit：`355e460e818eaed01a1c4cd7edc38615110c16ba`
- Review HEAD：`55bc0472efd9d75173aa265766964b7cf1fb4967`
- Draft PR：#63，mergeable／clean。
- Final PR CI：run `31181171984`／job `92874536776`，Python 3.10、Black與所有workflow steps成功。

## Work獨立驗證

- Repository Phase A evidence verifier：passed。
- PostgreSQL 16完整portal-data suite：106/106 passed。
- Compileall、isort與`git diff --check`：passed。
- Canonical verifier確認三份reviewed SQL checksums：
  - pre-check：`51ce7d88463f96bcf1a9cd12d0c3e1eeb5c17f5f0bdf19d466e7a0e296e6cd33`
  - migration：`81fa1ba1a2d2d856d4b4393cbdfbc663d6c19759f758f36b08e76e39a964636a`
  - post-check：`4ed0c186db2df4c735d8dd93857d060efd48c57d2a05972cc90617c6b3c83546`
- Work啟動的container/network已移除；既有local fake-data volume依契約保留。

## Finding補正確認

- Pre/post使用與TASK-052相同的legacy table／column／PK-FK fingerprints；migration後只接受已核准的
  `members.person_id`與相關constraints變化。
- Pre/post固定schema ownership、usage/create、legacy ownership、session／write／PUBLIC／other visible grant
  counts，並以repository外CSV比較legacy aggregate invariants。
- Post阻擋portal PUBLIC grants、非Owner direct grants及非Owner table default ACL；Owner implicit privileges不
  被誤判。
- Mutation tests實際涵蓋legacy column、constraint、direct grant、default ACL、RLS、policy、index與row drift。

## 剩餘風險與下一閘門

- Local PostgreSQL 15/16與hosted CI不能證明當下Supabase catalog、locks或SQL Editor執行行為。
- TASK-063須固定合併後commit與checksums、fresh pre-check、retained recovery artifact、maintenance boundary、
  stop/recovery及Owner exact approval。
- Production只能依序執行pre-check → Work離線驗證 → migration一次 → post-check → Work離線比較；任一步
  異常立即停止，不得ad-hoc修改或拆句重試。

## 安全聲明

未讀Owner CSV／archive／credential／env，未連Supabase／production，未執行production SQL／migration、
DDL/DML、stamp、backfill、deployment、notification或cloud mutation。

## 下一位角色

Work可依Owner長期Git授權完成PR #63 ready／squash merge，隨即建立TASK-063 exact production execution package；
production migration仍須Owner另行精確批准。
