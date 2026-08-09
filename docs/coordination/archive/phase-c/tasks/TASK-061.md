# TASK-061：取得 Phase A 合併後 execution-time baseline

## 任務目標

在 TASK-060 已由 PR #62 squash merge為 `0d54a4c017dc66dc0d25b037e93f09e1e62a6a12` 後，重新執行
既有 reviewed read-only catalog/access query，取得 Phase A production migration執行前的新鮮基線。Work只離線
驗證去識別化CSV；通過後才能提出exact production migration execution package。

## 已固定輸入

- Read-only SQL：`docs/operations/sql/TASK-052-supabase-readonly-access-boundary.sql`
- SQL SHA-256：`6b5da04cb357e2f261c0d37a7cf68ece3a534bc94a9fb2afb3def26e0d154260`
- Merged migration artifact：`docs/operations/sql/portal-data-0001-to-0003.sql`
- Artifact SHA-256：`81fa1ba1a2d2d856d4b4393cbdfbc663d6c19759f758f36b08e76e39a964636a`
- Repository base：`0d54a4c017dc66dc0d25b037e93f09e1e62a6a12`

## Owner操作

1. 在Supabase SQL Editor開啟新的query。
2. 從目前`main`完整複製上述TASK-052 SQL，不修改內容；第一句必須是
   `BEGIN TRANSACTION READ ONLY`，最後一句必須是`ROLLBACK`。
3. 執行一次。若出現warning、permission error、timeout、額外result set或unexpected prompt，停止且不要修改SQL重試。
4. 只將結果表匯出為CSV；header必須精確為：

```csv
section,metric,status,boolean_value,integer_value,text_value
```

5. 將CSV保留在repository外並交給Work。不得提供project ref、URL、DSN、role/account、password、token或
   SQL Editor周邊畫面。

## Work驗證

- 使用repository既有validator離線驗證exact 33 metrics／six-column contract。
- 必須確認transaction read-only、三個legacy fingerprints、10張legacy tables、RLS 10/10、zero policies、
  no Alembic marker與zero portal tables，且generic role boundary與TASK-059一致。
- Raw CSV不得複製或提交repository；只記錄去識別化pass/fail summary。

## 時效與失效條件

此baseline只在同一migration準備時段有效。結果取得後如發生deployment、schema／RLS／grant／role變更、手動SQL
維護、production incident，或執行前準備中斷，baseline立即失效並須重跑。

## 明確非目標

- 不執行migration、DDL/DML、stamp、backfill、RLS/policy/grant/role change。
- Work/Codex不讀credential、不連Supabase、不操作Dashboard。
- 不部署、不通知、不修改Secret／IAM／Scheduler／cloud resources。
- 通過baseline不自動授權production migration。

## 完成條件

Work確認CSV contract與全部expected metrics通過，沒有catalog/access drift；然後另行提出包含exact merged commit、
artifact SHA-256、transaction、timeouts、stop conditions、post-check與recovery boundary的production execution package，
等待Owner精確批准。
