# Cloud Functions Gen2 Source Rollback Runbook

狀態：`prepared_not_exercised`
適用目標：production `update-game-schedule`
Project／region：`ntubtob-schedule-405614`／`asia-east1`

## 1. 結論

Cloud Functions Gen2 沒有一般用途的「切回前一版 function revision」指令。受支援的 recovery 路徑是重新部署舊 source。Google Cloud Functions v2 API 的 `StorageSource` 明確包含 `bucket`、`object` 與 `generation`，而 `functions.patch` 可用 field mask 只更新 `buildConfig.source`。

官方參考：

- [gcloud functions deploy](https://docs.cloud.google.com/sdk/gcloud/reference/functions/deploy)
- [Cloud Functions v2 Function resource and StorageSource](https://docs.cloud.google.com/functions/docs/reference/rest/v2/projects.locations.functions)
- [Cloud Functions v2 functions.patch](https://docs.cloud.google.com/functions/docs/reference/rest/v2/projects.locations.functions/patch)

本機 Cloud SDK `481.0.0` 的 `gcloud functions deploy --source` parser 只建立 bucket/object，沒有設定 generation；將 `#generation` 附在 URI 會被視為 object 名稱的一部分。因此本 runbook 不使用該 CLI 語法回復特定 generation。

## 2. 已確認 recovery artifact

- Bucket：`gcf-v2-sources-556891917512-asia-east1`
- Object：`update-game-schedule/function-source.zip`
- Generation：`1741711972938401`
- Size：17,146 bytes
- MD5：`o5o7AvQja7+MFEI3mN6w0g==`
- Update time：2025-03-11 16:52:52 UTC
- Current build：`d82280ce-83ee-4e73-9214-609a0b934b35`
- Current function update time：2025-03-11 16:54:17 UTC

本次只讀 object metadata，沒有下載、解壓或讀取 archive 內容。

## 3. Bucket 保護

- Object versioning：enabled。
- Noncurrent lifecycle：只有存在超過 3 個 newer versions 時才刪除較舊 generation。
- Soft delete retention：604,800 seconds（7 days）。

在只進行下一次單一 deployment 的前提下，generation `1741711972938401` 應繼續保留。每次部署前仍必須重新 describe exact generation；若不存在即停止。

## 4. Current deployment contract

- Generation：Gen2。
- Runtime／entry point：Python 3.10／`main`。
- Runtime identity：default Compute Engine service account。
- Memory／CPU：256M／0.1666。
- Timeout：60 seconds。
- Max instances／concurrency：100／1。
- Ingress：`ALLOW_ALL`；resource IAM 沒有 public binding，Scheduler 使用 OIDC identity。
- Traffic：`allTrafficOnLatestRevision=true`。
- Secret reference：`DSN_PASSWORD=supabase-database-password:latest`。
- Scheduler：每日 10:00、16:00 Asia/Taipei，會執行 crawler 與 production DB writes。

Recovery 只更新 source，保留當時 function 的 service／trigger contract。若新 deployment 同時改變上述 contract，本 recovery 方法不再充分，必須停止並另寫完整 config rollback。

## 5. Rollback triggers

- 新 function 無法 `ACTIVE`／underlying revision 不 ready。
- Startup、import、entry point 或 config error。
- Private invocation boundary 或 Secret reference 退化。
- Scheduler 自然執行後出現可歸因於新版 filter 的錯誤。
- 無法證明新 deployment artifact 與批准 commit 的追溯關係。

Code rollback 不會撤回已發送通知，也不會自動復原 production DB writes。發現資料錯誤時先停止額外人工 invocation並回報 Owner；未經批准不得手動刪改資料或修改 Scheduler。

## 6. Recovery request

下列是經官方 API schema驗證的 request shape；**本任務沒有執行**。執行屬 production mutation，只能在 Owner 對 TASK-010 明確批准的 rollback 範圍內進行。

```json
{
  "name": "projects/ntubtob-schedule-405614/locations/asia-east1/functions/update-game-schedule",
  "buildConfig": {
    "source": {
      "storageSource": {
        "bucket": "gcf-v2-sources-556891917512-asia-east1",
        "object": "update-game-schedule/function-source.zip",
        "generation": "1741711972938401"
      }
    }
  }
}
```

Request：

```text
PATCH https://cloudfunctions.googleapis.com/v2/projects/ntubtob-schedule-405614/locations/asia-east1/functions/update-game-schedule?updateMask=buildConfig.source
```

實際執行工具應將 access token 保存在 process variable／Authorization header，不得輸出或寫入 repository。不得省略 `updateMask`，避免覆寫未包含於 request 的 function config。

## 7. Rollback 驗證

1. 等待 v2 long-running operation 完成。
2. 確認 function `ACTIVE`。
3. 確認 resolved source generation 是 `1741711972938401`。
4. 確認 runtime、entry point、service account、Secret reference、ingress 與 Scheduler target 未改變。
5. 確認 underlying revision ready 且由 function 控制面配置 traffic。
6. 不人工 invoke function；明確記錄線上 crawler／DB 行為未人工驗證。

## 8. 未驗證限制

- 尚未在 production 或 staging 實際執行 API PATCH，因為這會建立新 revision並改變 production。
- 尚未讀取舊 archive，因此沒有逐檔比對 source；artifact identity 以 production function resolved metadata、generation、size 與 hash為準。
- Repository 仍找不到舊 production source 的確切 Git commit。
- 若 lifecycle、generation、IAM 或 API contract 在部署前改變，必須重新評估。
