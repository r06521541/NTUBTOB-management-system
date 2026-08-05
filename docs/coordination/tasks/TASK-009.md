# TASK-009：部署 Notify Cron Secret Boundary

狀態：`completed`
優先級：P1
規劃者：Work
Production target commit：`086d663831cf49ddaa5f8413edd8508d1f6bf596`

## 任務目標

將 TASK-003 的 LINE credential build/runtime boundary 部署至 production `notify-cronjob-service`，並一併帶入 TASK-005 已驗收的未使用 import-time globals 清理。

## Production 基準

- Project／region：`ntubtob-schedule-405614`／`asia-east1`。
- Current revision：`notify-cronjob-service-00009-k8z`，ready，100% traffic。
- Current digest：`sha256:8da2b9448501cb793a73c037fdfbc84f1589cbe788510a8a74285978df15949a`。
- Current revision 為 2025-03-12（台北時間），尚未使用 LINE token runtime Secret reference。
- Service private；`CHANNEL_ACCESS_TOKEN` version 1 enabled，runtime identity 具 accessor。

## 執行範圍

- 從 exact commit `086d663` 建置並部署 `notify-cronjob-service`。
- 驗證新 revision ready／healthy、100% traffic、private IAM、runtime identity、database password 與 LINE token Secret references。
- 不人工呼叫 future announcement 或 attendance count endpoints。
- 失敗時將 traffic 切回 `notify-cronjob-service-00009-k8z`。

## Rollback 限制

`00009-k8z` 可作功能 rollback，但會恢復舊 credential boundary。它只能作緊急短期 rollback；rollback 後必須停止後續工作並回報 Owner。不得在本工作包輪替 LINE token，否則舊 revision 可能無法運作。

## Scheduler 與時窗

- `GameAttendanceCount`：週日、二、四 10:00。
- `WeeklyGameNotify`：週三 10:00。
- 建議 18:00–09:30 執行；距下一個 notify job 少於 30 分鐘即停止。
- Scheduler 不 pause。部署後會依既有排程自然呼叫新 revision，可能發出真實 LINE／Discord 通知；不包含人工觸發。

## Preflight／驗證

- [ ] Owner 明確批准 deployment、自然排程副作用與上述短期 rollback tradeoff。
- [ ] Exact source tree、Python 3.10 notify tests 4/4 與 CI success。
- [ ] Current revision／traffic、account/project/region、Secret enabled state 與 private boundary 重查無變動。
- [ ] Fresh shared artifact 建置與 hash。
- [ ] Temporary filtered env 成功建立並在任何結果下清理，不顯示內容。
- [ ] 記錄 build ID、revision、digest、traffic、IAM 與 Secret reference metadata。

## 非目標

不人工 invoke、不修改 Scheduler／IAM／Secret、不輪替 credentials、不部署其他元件、不存取 production data、不執行 migration。

## Owner 批准文字

```text
批准將 commit 086d663831cf49ddaa5f8413edd8508d1f6bf596 部署至 production 的 notify-cronjob-service，依 TASK-009 與 deployment runbook 執行 build、deploy、唯讀驗證；我接受緊急 rollback 至 notify-cronjob-service-00009-k8z 會短期恢復舊 credential boundary，且批准部署後既有 Scheduler 依原排程自然呼叫新 revision。不批准人工 invoke、Secret/IAM/Scheduler 修改、credential 輪替、其他服務部署或 production data 操作。
```

## 執行結果

- Owner 已明確批准本工作包與 security-degraded emergency rollback tradeoff。
- 2026-08-05 00:16–00:19（Asia/Taipei）完成 Cloud Build 與 deployment。
- Build `20152b06-02be-44d0-b50c-b92fc95877e7`：`SUCCESS`。
- 新 revision `notify-cronjob-service-00010-z2x`：ready／healthy，100% traffic。
- Image digest：`sha256:94751e129fe7d1d88304ebad716326f15023858252c6e28816b41d5220173fb5`。
- Service 維持 private；database password latest 與 LINE token version 1 均為 runtime Secret references。
- Scheduler、runtime identity 未變；沒有人工 invoke、通知、production data、Secret/IAM/Scheduler mutation。
- 未觸發 rollback；舊 revision `00009-k8z` 保留。
- Preflight 發現並移除既有 app temporary `.env.yaml` 殘留；原始 env source 保留且內容未顯示。部署後 temporary env 再次確認不存在。
