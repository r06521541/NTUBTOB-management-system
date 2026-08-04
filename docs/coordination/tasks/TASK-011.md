# TASK-011：準備 Cloud Functions Gen2 Rollback

狀態：`completed`
優先級：P1
執行者：Work（read-only first）
`base_commit`：`086d663831cf49ddaa5f8413edd8508d1f6bf596`

## 任務目標

為 production `update-game-schedule` 建立可稽核的 rollback 準備，解除 TASK-010 在 Gen2 function source／config 無法安全重現的 blocker。

## 工作範圍

- 查證 Google Cloud 官方對 Gen2 function source deploy／rollback 的支援方式。
- 唯讀確認 current source object generation 是否仍存在且可定址。
- 記錄 runtime、entry point、service account、ingress、Secret reference、resource limits、build/source artifact 與 Scheduler metadata。
- 建立 recovery command 草稿、停止條件與仍需 Owner 授權的步驟。
- 評估是否足以解除 TASK-010 blocker。

## 非目標與安全限制

- 不下載、解壓或讀取舊 source archive。
- 不讀取 Secret value、environment value、application logs 或 production data。
- 不 deploy、invoke、切 traffic、修改 Scheduler／IAM／Secret 或建立雲端 artifact。
- 不宣稱未實跑的 rollback 已驗證。

## 驗收條件

- [x] 官方或 CLI primary evidence 說明受支援的 source redeploy 方法。
- [x] 舊 object generation metadata 可唯讀取得。
- [x] 舊 function deployment contract metadata 完整記錄。
- [x] Recovery procedure 明確區分已驗證、未驗證與需 Owner 批准。
- [x] TASK-010 blocker 結論更新。

## 結論

- 舊 generation 存在且受 bucket versioning／lifecycle／soft delete 保護。
- 官方 v2 API 支援以指定 generation 更新 `buildConfig.source`。
- 現行 gcloud CLI 的 source parser 不設定 generation，故 recovery 應使用 v2 PATCH 與精確 field mask。
- Recovery request 未實跑，因為實跑會改變 production；它應只在 TASK-010 部署失敗時依 Owner 預先批准執行。
- TASK-010 可解除 blocker並進入 `awaiting_owner_approval`。
