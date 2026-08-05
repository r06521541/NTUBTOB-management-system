# TASK-007：Production 唯讀部署盤點

狀態：`awaiting_owner_decision`
優先級：P1
執行者：Work（read-only inventory）
`base_commit`：`086d663831cf49ddaa5f8413edd8508d1f6bf596`

## 任務目標

依 Owner 授權，以唯讀方式確認 production 的 Cloud Run、Cloud Functions、Scheduler、runtime identity、Secret metadata 與 rollback 基準，判斷 TASK-001 至 TASK-005 後需要重新部署的元件。

## 授權與安全邊界

- 允許讀取 deployment metadata、IAM boundary、Secret 名稱與版本狀態。
- 不讀取 Secret value、application logs 或 production data。
- 不部署、不切流量、不修改 Secret／IAM／Scheduler，也不發送通知或 invoke endpoint。

## 結論

- `game-broadcast-service`：production 已包含 2026-08-03 的 P0 Secret boundary，但早於 TASK-005；需要部署 request-time 修正。
- `notify-cronjob-service`：production revision 停在 2025-03-12（台北時間），尚未包含 TASK-003；需要部署 LINE Secret boundary。
- `update-game-schedule`：production function 停在 2025-03-12（台北時間），尚未包含 TASK-004；需要部署 team filter 修正。
- `web-portal`：沒有本輪功能部署需求，且仍受 Secret/build context blocker 禁止部署。
- `line-webhook-handler`：沒有本輪部署需求。
- Shared library 在盤點範圍內沒有 source change。

完整證據與風險見 `docs/operations/PRODUCTION_INVENTORY_2026-08-04.md`。

## Owner 待決事項

1. 是否先批准 `game-broadcast-service` 的獨立 production deployment 工作包。
2. `notify-cronjob-service` 是否在同一維護時段部署，並接受舊 revision 只可作短期功能 rollback、會恢復舊 Secret boundary 的限制。
3. `update-game-schedule` 是否先補強可重現 rollback，再另行批准 deployment。
