# TASK-018：部署 Game Broadcast Startup安全修正

狀態：`completed`
優先級：P1
規劃與執行：Work
Production target commit：`b14dcad3d1261772c8dc00898ba1caca114ce941`

## 任務目標

將已合併的side-effect-free health route與TASK-016 startup安全修正部署至production `game-broadcast-service`，使process startup不再因建立`LineBotAnnouncementHelper`而查詢production DB。

## 已確認基準

- Project／region：`ntubtob-schedule-405614`／`asia-east1`。
- Current serving revision：`game-broadcast-service-00030-pgg`，100% traffic。
- Rollback digest：`sha256:7301a529d18506f5f46832090421924cd7c40e2726233d0062fbc2ea1a4c8698`。
- `00031-s65`含health route且Ready，但先前authenticated `/healthz`於container前端回傳404，因此不承接traffic。
- TASK-015已排除source、image及Flask route缺漏；URL／frontend routing仍未完全確認。
- Target commit的Python 3.10 CI run `30975939328`成功；game broadcast 27/27 tests通過。

## 核准範圍

- 從exact main commit `b14dcad3d1261772c8dc00898ba1caca114ce941`隔離建置並部署。
- 依deployment runbook執行離線preflight、Cloud Build、Cloud Run deploy與唯讀control-plane驗證。
- 驗證new revision Ready／healthy、100% traffic、private boundary、runtime identity與Secret references未退化。
- 部署後既有Scheduler依原排程自然呼叫新revision；可能讀取production DB、發送既有LINE／Discord通知或寫入announcement timestamps。
- 符合失敗條件時，將100% traffic rollback至`game-broadcast-service-00030-pgg`。

## 本次刻意不做Health request

本工作包不人工呼叫`GET /healthz`。TASK-014的404發生於container之前且根因未完全確認；本次先以control-plane及container startup狀態驗收startup安全部署，避免把URL診斷與部署混為同一次mutation。若Owner之後仍要驗證health route，應另立單次canonical URL／proxy request工作包。

## 停止／Rollback條件

- Source不是exact approved commit，或build context含不明／敏感檔案。
- 受影響離線測試或既有Python 3.10 CI不通過。
- Account、project、region、rollback revision、Scheduler時窗或部署契約漂移。
- New revision未Ready／ContainerHealthy、未承接100% traffic，或private boundary、runtime identity、Secret references退化。
- 發生非預期通知、資料副作用，或無法建立commit→build→digest→revision追溯。

## 驗證與紀錄

- Game broadcast完整離線tests、compile及`git diff --check`。
- Fresh shared artifact及SHA-256。
- Cloud Build ID、new revision、digest、conditions與traffic。
- Service無public member；database、weather與LINE Secret reference名稱／版本不變。
- Temporary filtered env在任何結果下清理，內容不得輸出。

## 非目標

不人工invoke任何health或business route、不修改Secret／IAM／Scheduler、不輪替credential、不部署其他服務、不人工操作production data、不修改schema或migration。

## Owner精確批准文字

```text
批准將commit b14dcad3d1261772c8dc00898ba1caca114ce941部署至production的game-broadcast-service，依TASK-018與deployment runbook執行build、deploy及唯讀control-plane驗證，並在定義失敗條件下將100% traffic rollback至game-broadcast-service-00030-pgg。我接受部署後既有Scheduler依原排程自然呼叫新revision，並可能讀取production DB、發送既有LINE／Discord通知或寫入announcement timestamps。不批准人工invoke任何health或business route、Secret／IAM／Scheduler修改、credential輪替、其他服務部署或人工production data操作。
```

Owner已於2026-08-05批准上述精確範圍。

## 執行結果

- Cloud Build `b4081955-261f-4e41-a160-c31376e3b1ff`成功，built digest為`sha256:091a429733593c91aaba877a9224abca7951116ada9b42671131e462174d7799`。
- 固定`:tag1`使原deploy step未建立新revision；service仍安全維持`00030-pgg` 100% traffic。
- Work改以精確digest建立`game-broadcast-service-00033-mdp`，驗證契約後顯式切換100% traffic。
- `00033-mdp` Ready／Active／ContainerHealthy／ContainerReady均為True；private boundary、runtime identity、Secret references及Scheduler未退化。
- 未人工invoke、未修改Scheduler／Secret／IAM、未人工操作production data或發送通知。
- 未觸發rollback；`00030-pgg`保留。
