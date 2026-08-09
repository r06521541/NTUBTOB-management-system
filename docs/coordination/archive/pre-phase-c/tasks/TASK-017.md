# TASK-017：部署 Notify Cron Startup安全修正

狀態：`completed`
優先級：P1
規劃與執行：Work
Production target commit：`b14dcad3d1261772c8dc00898ba1caca114ce941`

## 任務目標

將已由Owner接受的side-effect-free health route與TASK-016 startup安全修正部署至production `notify-cronjob-service`。

## 核准範圍

- 從exact main commit `b14dcad3d1261772c8dc00898ba1caca114ce941`建置並部署。
- 依deployment runbook執行離線preflight、build、deploy及唯讀control-plane驗證。
- 部署後既有Scheduler依原排程自然呼叫新revision；Owner接受其可能讀取production DB並發送既有正式LINE通知。
- 符合失敗條件時，將100% traffic rollback至`notify-cronjob-service-00010-z2x`。

## 停止／Rollback條件

- Target source不是精確approved commit，或working tree／build context有不明變更。
- Python 3.10 CI或受影響離線測試失敗。
- Account、project、region、private boundary、runtime identity或必要Secret reference漂移。
- 新revision未Ready、未承接100% traffic、container health失敗或部署契約退化。
- 發生未批准的人工invoke、雲端設定變更或資料操作。

## 驗證

- Notify cron完整離線tests與compile check。
- `git diff --check`與exact source tree確認。
- Cloud Build success、new revision Ready／healthy、100% traffic。
- Service維持private，runtime identity與Secret reference名稱／版本不退化。
- Temporary filtered env在任何結果下移除；不顯示內容。

## 非目標

不人工invoke、不修改Secret／IAM／Scheduler、不輪替credential、不部署其他服務、不人工操作production data、不執行schema或migration變更。

## Owner批准

Owner於2026-08-05批准上述exact commit、target、自然Scheduler副作用、rollback與排除範圍。

## 執行結果

- Cloud Build `3d751cb3-6b47-4de5-9568-e25425ef63c5`成功。
- Revision `notify-cronjob-service-00011-jpj` Ready／healthy並承接100% traffic。
- Image digest：`sha256:8f7d551c41bb6e911d1a2cbc8a22c2b0911ea98650c6e27d613b4c5e6057c596`。
- Private boundary、runtime identity與Secret references未退化；temporary env已清理。
- 未人工invoke、未修改Scheduler／Secret／IAM、未人工操作production data或發送通知。
- 未觸發rollback；`00010-z2x`保留。
