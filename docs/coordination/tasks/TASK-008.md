# TASK-008：部署 Game Broadcast Request-Time 修正

狀態：`completed`
優先級：P1
規劃者：Work
Production target commit：`086d663831cf49ddaa5f8413edd8508d1f6bf596`

## 任務目標

依已採納的 deployment runbook，將 TASK-005 的 request-time 修正部署至 production `game-broadcast-service`，同時維持既有 P0 Secret boundary、private IAM 邊界與 11 天邀請視窗。

## 已確認 production 基準

- Project／region：`ntubtob-schedule-405614`／`asia-east1`。
- Current serving revision：`game-broadcast-service-00029-vmc`，100% traffic。
- Current image digest：`sha256:02de096bf0b42cb34c659a2580856eda7c2171be74e08aab8d4d71e8351eb8df`。
- Current runtime Secret references：Weather API key version 2、LINE channel access token version 1、database password latest；查詢時均為 enabled。
- Current service 為 private；Scheduler 使用 OIDC identity 呼叫。

## 執行範圍

- 從 exact commit `086d663` 建置 game broadcast image。
- 重新建置並放入既有 shared library artifact；shared library source 本輪沒有變更。
- 執行 repository 的 `deploy-game-broadcast-service` target，建立新 Cloud Build、image 與 Cloud Run revision。
- 部署後以唯讀 metadata 驗證 revision ready、100% traffic、private boundary、runtime identity 與 Secret reference metadata。
- 若新 revision 不 ready、private boundary 退化、Secret binding 缺失或 startup 狀態異常，將 100% traffic 切回 `game-broadcast-service-00029-vmc`。

## 明確非目標

- 不呼叫 invitation、cancellation 或 reminder endpoints。
- 不主動發送真實 LINE／Discord 通知。
- 不修改或讀取 Secret value，不輪替 credentials。
- 不修改 Scheduler、IAM、database、schema、Web Portal、其他 services/functions。
- 不執行 production data write 或 destructive operation。

## 執行前條件

- [ ] Owner 明確批准本次 production deployment 與必要 rollback traffic switch。
- [ ] 使用 exact target commit `086d663`，且部署範圍內沒有未提交變更。
- [ ] GitHub Actions run `30922220358` 仍為 success。
- [ ] 重新執行 game broadcast 24 tests 並通過。
- [ ] gcloud active account、project 與 region 再次確認。
- [ ] Current revision 仍為 `00029-vmc`、ready 且 100% traffic；若已變動即停止並重新請示。
- [ ] Secret versions 2／1／latest 仍 enabled，runtime identity 仍具 accessor；不讀 value。
- [ ] 部署時段不得接近既有 Scheduler invocation。
- [ ] 確認 temporary `.env.yaml` 的來源與 build exclusion；不輸出內容。

## 建議執行時段

Asia/Taipei 18:00 至隔日 09:00，避開每日 09:30 reminder、16:30 cancellation 與 17:30 invitation。若實際開始時距下一個 game broadcast job 少於 30 分鐘，停止並改期。

Scheduler 不會在本工作包中被 pause。部署完成後，既有 Scheduler 將在下一次排程自然呼叫新 revision，屆時可能發出真實通知；Owner 的部署批准必須接受此正常排程結果，但不包含人工觸發。

## 部署後驗證

- 新 revision 顯示 ready 且取得 100% traffic。
- Service 維持 private，沒有 `allUsers` invoker。
- Runtime service account 未改變。
- Weather、LINE 與 database password Secret references 維持預期名稱／版本。
- 記錄 Cloud Build ID、image digest、新 revision、開始／完成時間。
- 確認 `apps/game_broadcast_service/.env.yaml` temporary file 已清理。
- 不以 endpoint smoke test 驗證業務行為，交付時明確標示線上通知流程尚未人工驗證。

## Rollback

觸發條件：revision 不 ready、startup/config error、Secret reference 缺失、public boundary 退化、非預期通知／資料副作用，或無法建立 artifact traceability。

Rollback target：`game-broadcast-service-00029-vmc=100`。切回後重新確認 traffic、ready、private boundary 與 Scheduler target；不刪除失敗 revision。

## 需要 Owner 批准的文字

```text
批准將 commit 086d663831cf49ddaa5f8413edd8508d1f6bf596 部署至 production 的 game-broadcast-service，依 TASK-008 與 deployment runbook 執行 build、deploy、唯讀驗證，並在定義的失敗條件下將 100% traffic rollback 至 game-broadcast-service-00029-vmc。批准部署後既有 Scheduler 依原排程自然呼叫新 revision；不批准人工 invoke、Secret/IAM/Scheduler 修改、其他服務部署或 production data 操作。
```

## 已知限制

- Image tag 仍為固定 `tag1`；本次須以 build ID、digest 與 revision 補足追溯。
- Current production artifact 沒有 Git SHA label；P0 已部署的判斷主要依 commit/build/revision 時間與現行 Secret references。
- 現有工作目錄包含尚未提交的協作文件與 Owner 隊徽，正式部署前必須建立不會把這些內容帶入 build 的乾淨執行狀態。

## 執行結果

- Owner 於 2026-08-04 明確批准本工作包。
- 2026-08-04 23:48–23:52（Asia/Taipei）完成 Cloud Build 與 deployment。
- Build ID：`80b086fc-f0c1-4f6b-a4e6-3acb456a1d6b`，結果 `SUCCESS`。
- 新 revision：`game-broadcast-service-00030-pgg`，ready／healthy，100% traffic。
- 新 image digest：`sha256:7301a529d18506f5f46832090421924cd7c40e2726233d0062fbc2ea1a4c8698`。
- Private IAM、runtime identity 與 Secret references 維持預期；temporary env 已清理。
- 沒有人工 invoke、通知、production data、Secret/IAM/Scheduler mutation；未執行 rollback。
- 線上通知業務流程沒有人工 smoke test，將由既有 Scheduler 在原排程自然觸發。
