# TASK-011 Work Review

日期：2026-08-05
結論：`accepted_with_unexercised_recovery`
下一位角色：Owner

## 已驗證

- 官方 `gcloud functions deploy` 支援從 GCS zip 重新部署 source。
- 官方 Cloud Functions v2 `StorageSource` 支援精確 generation，`functions.patch` 支援 field mask。
- Old source generation `1741711972938401` 可唯讀 describe，metadata 與 production function resolved source一致。
- Bucket versioning enabled；lifecycle 保留最近 3 個 noncurrent generations，另有 7 天 soft delete。
- Runtime、entry point、resources、identity、Secret reference、ingress、traffic policy與 Scheduler contract 已記錄。
- 本機 gcloud CLI parser 不會把 URI fragment 轉成 `StorageSource.generation`，因此不使用未證實的 `gs://...#generation` deploy 語法。

## 未執行

- 沒有下載／讀取 source archive、Secret、env values、logs 或 data。
- 沒有 deploy、API PATCH、invoke、traffic、IAM、Secret 或 Scheduler mutation。
- Recovery API request 未實跑；這是刻意限制，不代表 production rollback 已演練。

## 判定

Rollback 已從「沒有可定位 source」提升為「具官方 API、精確 immutable generation 與完整 contract 的可執行 recovery plan」。在下一次 deployment 前重新確認 generation 與 contract，並由 Owner 預先批准條件式 PATCH rollback，可解除 TASK-010 blocker。
