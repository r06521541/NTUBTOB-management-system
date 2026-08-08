# TASK-073：執行 Phase C production migration

## 任務目標

依已驗收的 readiness runbook，在單一受控 migration window 內取得 fresh production inventory、執行精確的 `0003 -> 0004` transaction，並以 read-only post-check 證明結果。此任務只處理 database migration，不部署 application、不開啟 Phase C runtime flags。

## 精確版本與 artifacts

- Merged commit：TASK-074 squash merge後重新鎖定；未填入exact 40-character commit前不得執行
- Inventory SQL SHA-256：`9dc3d2e589ca298e40a9bf529d5801e6b7081016547996bbd5010df7adae2d46`
- Migration SQL SHA-256：`67ea4490a1e3459221f440ae280e95f3be5a868ad2c37c78ae3519073e7d1f91`
- Post-check SQL SHA-256：`6de46c7c46c5ea1dd75e0172a1369368c3d3d4ec7f1ddf8077afe4bcec613166`
- Runbook：`docs/operations/data/PORTAL_DATA_PHASE_C_PRODUCTION_READINESS.md`

任何 commit 或 checksum 改變都使本任務批准失效，必須重新驗收與批准。TASK-074
合併後必須填入exact merged commit，並取得新的30分鐘fresh inventory；先前CSV已失效。

## 執行階段與停損點

1. Owner 確認 backup verification 仍有效，並在 Supabase SQL Editor 執行精確 inventory SQL，匯出去識別化六欄 CSV。
2. Work 在 30 分鐘 freshness window 內 strict validate inventory；任何 required gate 失敗即停止。
3. Work 提交 evidence 結果，Owner 再明確批准該次 migration window 與上述 exact migration checksum。
4. Owner 在同一 Supabase SQL Editor session 執行 migration SQL一次；SQL 使用 transaction-local `lock_timeout = 5s`、`statement_timeout = 60s`。
5. 立即執行精確 post-check SQL並匯出六欄 CSV；Work strict validate及compare。
6. 若結果為 `pass`，database migration完成但runtime flags仍維持關閉；後續 application deploy及activation另立任務。

## Recovery boundary

- SQL在commit前明確失敗／timeout：transaction rollback，重新取得fresh inventory後才可重試。
- 連線中斷或commit結果不明：禁止重跑migration；先以read-only revision／post-check判定。
- Revision已為0004但semantic check失敗：保持feature-off，不執行destructive downgrade；建立另行批准的forward-recovery task。
- 不使用DELETE、TRUNCATE、ad-hoc cleanup、restore或production downgrade處理不明狀態。

## 非目標與禁止事項

- 不部署Web Portal、LINE webhook、notify cron或其他服務。
- 不開啟`PORTAL_DATA_PHASE_C_ENABLED`或identity-maintenance flag。
- 不修改Secret、IAM、Scheduler、Supabase API exposure、RLS policy或grants。
- 不發送LINE／Discord通知，不人工invoke webhook／scheduler。
- 不在repository、log或對話中保存connection string、credential、原始個資或application rows。

## 驗收條件

- Inventory於30分鐘內且所有required gates通過。
- Migration只執行一次，結果無ambiguous commit。
- Post-check exact catalog fingerprints、attendance bridge、Phase B invariants與stable aggregates全部通過。
- Compare結果為`pass`，並留下去識別化evidence與Work review。
- Runtime flags維持關閉，未發生deployment或其他production mutation。

## 目前需要 Owner 決策

先批准第一階段的 production read-only inventory collection。這項批准不包含 migration；Work驗證fresh inventory後，會提供第二次精確 migration批准文字。

## Base commit

`36016ee80911f98db1f638b43550e77fc75e87b1`
