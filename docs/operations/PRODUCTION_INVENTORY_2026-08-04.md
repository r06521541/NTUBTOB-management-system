# Production Deployment Inventory — 2026-08-04

狀態：`read_only_complete`
Project／region：`ntubtob-schedule-405614`／`asia-east1`
Repository target：`main` merge commit `086d663831cf49ddaa5f8413edd8508d1f6bf596`

## 1. 執行邊界

本次依 Owner 明確批准執行 production 唯讀盤點。只查詢 deployment、Scheduler、IAM、Secret reference/version state 與 build metadata；沒有讀取 Secret value、application logs 或 production data，也沒有部署、invoke、流量、IAM、Secret、Scheduler 或其他 mutation。

本機 gcloud 登入憑證過期，Owner 於盤點過程批准重新登入；登入只更新本機 credential。

## 2. 部署判定

| 元件 | Production 基準 | Repository 新事實 | 判定 |
| --- | --- | --- | --- |
| `game-broadcast-service` | revision `00029-vmc`，2026-08-03 23:53 台北時間，100% traffic | P0 commits 早於該 revision；TASK-005 functional commit `ba40ed3` 晚於該 revision | **需要部署**，範圍是 TASK-005 request-time 修正。 |
| `notify-cronjob-service` | revision `00009-k8z`，2025-03-12 00:41 台北時間，100% traffic | TASK-003 與 TASK-005 均晚於 production | **需要部署**，主要是 TASK-003 LINE Secret boundary；另包含移除未使用 import-time snapshot。 |
| `update-game-schedule` | Gen2 ACTIVE，2025-03-12 00:54 台北時間 | TASK-004 functional commit `11e9636` 晚於 production | **需要部署** team filter 修正，但 rollback 可重現性需先處理。 |
| `web-portal` | revision `00026-rtc`，2025-03-12 00:49 台北時間，public | 本輪沒有必要功能變更；現行 plain runtime login/session Secret 與 build context 仍不安全 | **禁止部署**，先修 blocker。 |
| `line-webhook-handler` | Gen2 ACTIVE，2025-10-24 00:27 台北時間，public | 本輪沒有 source change | **不需部署**。 |

Production artifact 沒有可靠 Git SHA label，因此「P0 已包含」是依 commit、Cloud Build 與 revision 時間的強證據推論，不是 artifact 內建 provenance。TASK-003／004／005 晚於 production timestamp，則可確認尚未部署。

## 3. Cloud Run rollback 基準

| Service | Current revision | Image digest | Traffic | Rollback 評估 |
| --- | --- | --- | --- | --- |
| game broadcast | `game-broadcast-service-00029-vmc` | `sha256:02de096bf0b42cb34c659a2580856eda7c2171be74e08aab8d4d71e8351eb8df` | 100% | 可作 TASK-005 部署的 previous serving revision。 |
| notify cron | `notify-cronjob-service-00009-k8z` | `sha256:8da2b9448501cb793a73c037fdfbc84f1589cbe788510a8a74285978df15949a` | 100% | 功能上可切回，但會恢復舊 LINE credential boundary，不是安全等價 rollback。 |
| web portal | `web-portal-00026-rtc` | `sha256:2d775811e40d62479f4a707034a31b14681ca3b65111220bc284b0bb450adcef` | 100% | 僅記錄；目前不得部署。 |

所有 current revisions 顯示 ready。這只證明平台狀態，不等於業務流程已驗證。

## 4. Functions rollback 基準

`update-game-schedule` 目前 source artifact metadata：

- Build：`d82280ce-83ee-4e73-9214-609a0b934b35`
- Object：`update-game-schedule/function-source.zip`
- Generation：`1741711972938401`
- Current underlying revision：`update-game-schedule-00027-nuf`
- Current image digest：`sha256:3d0873332bf215570b508c88240a6ab508b777a223654985de5c8be36270d145`

這些 metadata 已建立調查基準，但 repository 尚未證明可由該 artifact generation 安全重建舊 function；因此不將它宣稱為已驗證 rollback。部署 TASK-004 前，應先建立可重現的 previous source／command，或取得 Owner 對 rollback 限制的明確接受。

## 5. Scheduler 與副作用

以下 production jobs 為 enabled，時區均為 Asia/Taipei：

| Job | Schedule | Target effect |
| --- | --- | --- |
| `UpdateGameSchedule` | 每日 10:00、16:00 | crawler 與 production schedule data write。 |
| `BroadcastGameReminder` | 每日 09:30 | 可能發送真實 LINE／Discord reminder。 |
| `BroadcastGameCancellation` | 週一至週五、週日 16:30 | 可能發送取消通知。 |
| `BroadcastGameInvitation` | 週一至週五、週日 17:30 | 可能發送邀請通知。 |
| `GameAttendanceCount` | 週日、二、四 10:00 | 可能發送出席統計。 |
| `WeeklyGameNotify` | 每週三 10:00 | 可能發送未來賽程公告。 |

另有一個名為 `Test` 的 paused legacy job；本次未修改或刪除。

部署本身不 invoke endpoint，但新 revision 接收 100% traffic 後，這些既有 jobs 會按排程自然觸發。部署時段必須避開下一個 job，並把「正常排程可能在部署後發送通知／寫資料」納入 Owner 的部署批准。

## 6. IAM 與 Secret metadata

- 三個候選元件與現有 services/functions 使用 default Compute Engine service account 作 runtime identity。
- Project level 已授予該 identity `roles/secretmanager.secretAccessor`；權限範圍偏廣，後續應改為 dedicated least-privilege identities。
- Game broadcast current revision 已將 `WEATHER_API_KEY` version 2 與 `CHANNEL_ACCESS_TOKEN` version 1 作為 runtime Secret references；兩版本均 enabled。
- Notify cron current revision 的 `CHANNEL_ACCESS_TOKEN`／`CHANNEL_SECRET` 不是 Secret references，符合它尚未部署 TASK-003 的判定。
- Web portal current revision 的 LINE Login secret 與 Flask session key 不是 Secret references，維持 deployment blocker。
- 本次只查詢 version state，未讀取任何 Secret value。

## 7. 建議

### 第一個 deployment：game broadcast

三者中風險最低：現行 P0 Secret boundary 已在線，previous revision 可直接作 traffic rollback；待部署內容只剩 TASK-005 request-time 修正。仍須另外取得 Owner 對 exact commit、時段、preflight、部署與 rollback 的明確批准。

### 第二個 deployment：notify cron

安全價值高，但 current revision 是舊 Secret boundary。部署前需接受 rollback tradeoff，並避免在 Scheduler 即將觸發前操作。部署後不得以正式通知 route 作 smoke test。

### 第三個 deployment：update schedule

資料正確性價值高，但會由 Scheduler 寫入 production DB，且 Gen2 rollback 尚未完全證明。建議先完成 rollback source 可重現性，再另行批准部署。

## 8. 尚未執行

- 沒有讀取 application logs 或 Secret values。
- 沒有下載舊 Functions source archive。
- 沒有 invoke endpoints、發通知或存取 production DB。
- 沒有部署、切 traffic、修改 IAM／Secret／Scheduler。
- 沒有驗證 LINE、crawler 或 database 的線上業務流程。
