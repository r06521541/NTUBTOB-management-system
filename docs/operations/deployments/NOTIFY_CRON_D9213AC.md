# notify-cronjob-service feature-off deployment — 2026-08-08

## 結果

成功。

- Target：production `notify-cronjob-service`
- Approved source commit：`d9213acea1708f051fc457753b3b941dbad305f6`
- Cloud Build：`4ebde37e-1752-4a4c-9f8a-d4b39e9b1efe` (`SUCCESS`)
- Previous healthy revision／rollback baseline：`notify-cronjob-service-00012-gfm`
- New revision：`notify-cronjob-service-00013-ddr`
- Traffic：new revision 100%
- Image digest：`sha256:8841e04c0a9e1ed286694f0a30c1cc1a5b5e0a2380423f919c34ca7f55e68636`

## 已驗證

- gcloud active project 為 `ntubtob-schedule-405614`，target region 為 `asia-east1`。
- 部署前舊 revision Ready、100% serving；target IAM policy 沒有 public invoker binding。
- 新 revision 的 Ready、Active、ContainerHealthy、ContainerReady 與 ResourcesAvailable conditions 均為 True。
- Artifact Registry 的 approved Git SHA tag 與新 revision 的 image digest 完全一致。
- runtime metadata 的 key name list 包含 `CHANNEL_ACCESS_TOKEN`、`PORTAL_DATA_PHASE_C_ENABLED` 與
  `PORTAL_DATA_ROLLOUT_FREEZE_ENABLED`。
- `CHANNEL_ACCESS_TOKEN:2` 是本次已合併 Cloud Build contract 的明確 binding；未讀取 Secret payload。
- 針對新 revision 的 deployment-time `ERROR` log metadata 查詢沒有結果。
- Cloud Build 成功後，因本機 wrapper 等待逾時遺留的精確暫存檔
  `apps/notify_cronjob_service/.env.yaml` 已不讀內容地清除。

## feature-off 判定與限制

- Owner 在部署前已確認三份 controlled non-secret env source 都將 Phase C／freeze flags 設為 `false`；這是本次
  deployment 的輸入前提。
- 為遵守不讀取 private `.env.yaml` 及不輸出完整 runtime env 的安全邊界，Work只核對新 revision存在兩個 flag key，
  不讀取或記錄其 runtime value。故 feature-off 值的證據為 Owner 的前置設定加上 Cloud Build成功，而非 Work直接讀值。
- 未啟用 Phase C、freeze 或 identity maintenance；沒有執行任何 Portal／Webhook／notify POST、Scheduler操作、
  production DB操作或 LINE／Discord通知。

## 未執行

- 無 side-effect endpoint invoke，故不宣稱實際排程通知或出席統計業務流程已在線上驗證。
- 未修改 Secret、IAM、Scheduler、schema、資料或其他服務。

## rollback

若後續發現問題，將 100% traffic 切回已記錄的
`notify-cronjob-service-00012-gfm`；本次未觸發 rollback。
