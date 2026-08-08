# LINE credential rotation deployment record（2026-08-08）

## 結論

Owner已在LINE平台輪替Messaging API credentials，並在Secret Manager建立enabled version `2`。production
LINE webhook、game broadcast與notify cron已改用`CHANNEL_ACCESS_TOKEN:2`；LINE webhook另已改用
`CHANNEL_SECRET:2`。本文件不記錄任何Secret value。

## 已執行的production變更

| Target | New revision / state | Credential result | Verification |
| --- | --- | --- | --- |
| `line-webhook-handler` Gen2 | `line-webhook-handler-00009-fiv`，`ACTIVE` | `CHANNEL_ACCESS_TOKEN:2`與`CHANNEL_SECRET:2`均為Secret Manager binding；兩個plain key不存在 | Phase C／freeze flags均為`false`；`ALLOW_ALL`與`allUsers` invoker維持；五分鐘ERROR為0 |
| `game-broadcast-service` Cloud Run | `game-broadcast-service-00034-6rf`，100% traffic | `CHANNEL_ACCESS_TOKEN:2`；`CHANNEL_SECRET`不存在 | private IAM維持；五分鐘ERROR為0 |
| `notify-cronjob-service` Cloud Run | `notify-cronjob-service-00012-gfm`，100% traffic | `CHANNEL_ACCESS_TOKEN:2`；`CHANNEL_SECRET`不存在 | private IAM維持；五分鐘ERROR為0 |

Web Portal feature-off deployment亦已完成於`web-portal-00042-r69`，三個Phase C／freeze／maintenance flags皆為
explicit `false`；本輪沒有改動其LINE Login Secret。

## 控制與限制

- 未人工invoke webhook、Scheduler或任何業務endpoint，未發送測試通知。
- 未讀取、輸出、提交或記錄任何Secret value；gcloud原始deploy輸出一律導向temporary local file並於完成後刪除。
- LINE webhook的source rollback candidate仍是TASK-078記錄的immutable GCS generation
  `1761236780707683`；不得以舊plaintext credential configuration作為rollback理由。
- Cloud Run token rotation不應自動切回version `1`，因其已被Owner輪替並即將或已失效。

## 後續必要工作

1. 修正`apps/game_broadcast_service/cloudbuild.yaml`與
   `apps/notify_cronjob_service/cloudbuild.yaml`內的`CHANNEL_ACCESS_TOKEN:1`為受控的version `2`策略，並補測試，
   避免下次source deployment回退到version `1`。
2. 完成尚未部署的notify Phase C feature-off artifact／freeze boundary；本次notify只做credential binding revision update，
   沒有部署TASK-077 application source。
3. 評估將LINE webhook的Windows direct deploy改為不會回顯完整function config的正式wrapper，並將credential rotation
   flow納入runbook。
