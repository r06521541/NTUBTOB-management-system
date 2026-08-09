# TASK-010：部署 Update Schedule Team Filter

狀態：`completed`
優先級：P1
規劃者：Work
Production target commit：`086d663831cf49ddaa5f8413edd8508d1f6bf596`

## 任務目標

將 TASK-004 的 team/date filter 修正部署至 production `update-game-schedule` Gen2 function，避免非本隊賽程進入新增／取消處理。

## Production 基準

- Function ACTIVE，最後更新 2025-03-12 00:54（Asia/Taipei）。
- Current underlying revision：`update-game-schedule-00027-nuf`。
- Current digest：`sha256:3d0873332bf215570b508c88240a6ab508b777a223654985de5c8be36270d145`。
- Current source object generation：`update-game-schedule/function-source.zip#1741711972938401`。
- Scheduler `UpdateGameSchedule` 每日 10:00、16:00 執行，會呼叫 crawler 並寫入 production DB。

## Blocking 問題

Repository 找不到 current production source 對應的可靠 Git commit；現有 gcloud help 只確認 `--source=gs://...`，沒有證明指定舊 object generation 可作可重現 rollback。依 runbook「無 rollback 路徑不得部署」，目前不得執行 deployment。

不採用底層 Cloud Run traffic switch 作正式 rollback，因 Cloud Functions Gen2 控制面是否支援該方式尚未查證。

## Blocker 解除結果

TASK-011 已確認 old source generation 存在、bucket versioning 保護，以及官方 Functions v2 API 可用精確 generation PATCH `buildConfig.source`。Rollback 不使用底層 Cloud Run traffic switch，也不使用本機 gcloud CLI 未支援的 generation URI parsing。

完整 recovery contract：`docs/operations/GEN2_FUNCTION_ROLLBACK.md`。

Recovery 尚未實跑，因為實跑本身就是 production deployment。Owner 必須在 TASK-010 deployment 批准中預先授權：符合 rollback trigger 時，以 exact old generation執行 v2 PATCH，並接受 code rollback 不會復原已寫入資料。

## 解除條件

至少完成其中一項並驗證：

1. 建立不讀取內容、但可從 immutable old source generation 重建 function 的受控 rollback procedure；或
2. 找到並驗證與 current production artifact 一致的 repository commit 及 deployment contract；或
3. 由 Owner 明確接受「無已驗證 rollback」的重大 production data 風險。Work 不建議第三項。

解除 blocker 後仍需另一份 exact production deployment 批准，包含 Scheduler 自然觸發 crawler／DB write；不得人工 invoke。

## 目前未授權／未執行

沒有下載或讀取舊 source archive、沒有人工 crawler／DB invocation，也沒有 Scheduler／IAM／Secret mutation。Owner 已批准 deployment 與條件式 rollback；deployment 已成功，未觸發 rollback。

## 部署結果

- Build：`7d26952d-f9d3-4a40-a941-26db20630636`（`SUCCESS`）。
- Revision：`update-game-schedule-00028-bij`。
- Image digest：`sha256:1a6cea978ad987425359cb70efddf6a3b22c1de0af5d4f4a8a8c77a920547885`。
- Source generation：`1785861160031448`。
- Function 與 revision 為 ACTIVE／Ready；runtime、entry point、runtime identity、Secret reference、resource limits 與 private IAM boundary 未退化。
- Scheduler 維持 enabled、每日 10:00／16:00 Asia/Taipei及原 OIDC target；未人工 invoke。
- 沒有觸發 rollback；舊 generation `1741711972938401` 保留為 recovery target。

## Owner 批准文字

```text
批准將 commit 086d663831cf49ddaa5f8413edd8508d1f6bf596 部署至 production 的 update-game-schedule，依 TASK-010、deployment runbook 與 Gen2 rollback runbook 執行 build、deploy及唯讀驗證；若符合 rollback trigger，批准以 Cloud Functions v2 PATCH 將 buildConfig.source 回復至 GCS generation 1741711972938401。我接受既有 Scheduler 會於每日 10:00、16:00 自然呼叫新 function並可能寫入 production DB，也理解 code rollback 不會自動復原已寫入資料。不批准人工 invoke、Scheduler/IAM/Secret 修改、手動資料修復或其他服務部署。
```
