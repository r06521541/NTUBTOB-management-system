# TASK-059 Work review

## 結論

`accepted` 作為 2026-08-07 當下 production read-only catalog/access baseline。Raw CSV位於 repository外，
repository只保存以下去識別化 summary。本結果不授權 migration，且在 migration artifact補正與 PR/CI期間
不再視為 execution-time baseline；正式執行前必須重跑。

## 輸出 contract

- Repository validator：passed。
- Exactly 33 metrics／6 fixed columns；值域與 one-value-per-row contract：passed。
- Transaction read-only：true；server major：15。
- 未發現 URL、DSN、role/account identity、Secret或 application row values。

## Catalog freshness

- `ntubtob` exists：true。
- Legacy tables：10。
- Table／column／PK-FK fingerprints：全部 match。
- `alembic_version` exists：false。
- New portal tables：0。
- Legacy RLS enabled：10／10；forced：0；policy count：0。

## Generic execution-role boundary

- Session superuser：false。
- Session bypasses RLS：true。
- Session can create role／database：true／true。
- Schema owner relation：same；session owns 10／10 legacy tables。
- Session對10張 legacy tables具 SELECT／INSERT／UPDATE／DELETE／TRUNCATE；PUBLIC grants 0、other visible
  grants 0、visible write grants 40。

這是高權限 migration-owner邊界，不是低權限 read-only role。此次 query 的安全性由 transaction-level
READ ONLY與 ROLLBACK保證；未來 mutation的安全性只能依賴 exact reviewed artifact、single transaction、
timeouts與 Owner明確接受此角色風險。

## Blocking artifact findings

- 現有 `portal-data-0001-to-0003.sql` 已由 repository verifier成功重現並驗證 sidecar；Windows raw-byte hash差異
  是 checkout line ending，canonical verifier通過。
- Production沒有 `ntubtob.alembic_version`，但現有 artifact從 `0001_legacy_baseline` 到 `0003`，只含兩次
  version `UPDATE`，沒有在同一 transaction建立／記錄 baseline。因此目前 artifact不能直接在production成功。
- 13張新 portal tables目前沒有 `ENABLE ROW LEVEL SECURITY`；這和RLS decision package的fail-closed建議尚未
  收斂。不得在 execution時 ad-hoc附加SQL。

## 下一步與時效

Owner需先決定是否：

1. 接受使用目前 SQL Editor migration-owner role執行一次 exact reviewed transaction；
2. 要求 Phase A 即為全部13張新表 enable RLS且建立零 policies（推薦）。

確認後另開 TASK-060，將 baseline marker與RLS納入 deterministic artifact、verifier、local rehearsal與CI。
TASK-060合併後，Owner需重跑 TASK-059 SQL取得真正 execution-time baseline。

## 安全聲明

Work只離線讀取並驗證 Owner提供的 generic CSV；未登入／連線 Supabase、未讀 credential、未執行 SQL／DDL／
migration、未修改 raw CSV或提交其內容。
