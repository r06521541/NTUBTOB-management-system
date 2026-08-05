# TASK-014：部署 Game Broadcast Health Check

狀態：`completed`（deployment rolled back）
優先級：P1
規劃者：Work
執行者：Work（依production deployment runbook）
Production target commit：`974433168b86e5638adce779ed8eccced0542094`

## 1. 任務目標

將TASK-013的side-effect-free `GET /healthz`部署至production private Cloud Run service `game-broadcast-service`，並在不呼叫invitation／cancellation／reminder業務routes的前提下，使用具授權身分執行一次authenticated health smoke check。

## 2. Owner核准範圍

Owner已批准第10節的精確production deployment範圍，包括build、deploy、control-plane驗證、一次authenticated `GET /healthz`，以及符合trigger時將100% traffic切回`game-broadcast-service-00030-pgg`。未批准業務routes人工invoke、其他服務、Secret／IAM／Scheduler修改、production data操作或application log讀取。

## 3. Repository與CI基準

- `main` merge commit：`974433168b86e5638adce779ed8eccced0542094`。
- PR #30已merge；最終Python 3.10 run `30970166514`／job `92192551181`成功。
- 相較上次production target `086d663`，game broadcast deployment source只新增：
  - `GET /healthz` Blueprint與registration。
  - Offline actual-app route tests。
  - Service README。
- `shared_lib`、business routes、notification templates、Scheduler、Cloud Build及Docker deployment config沒有變更。
- Local Work驗證：game broadcast 26/26、notify cron 6/6通過（Python 3.12.13）；Python 3.10證據來自CI。

## 4. Production唯讀preflight（2026-08-05）

- Project／region：`ntubtob-schedule-405614`／`asia-east1`。
- Active account：`yces3108@gmail.com`。
- Current serving revision：`game-broadcast-service-00030-pgg`，Ready／Active／ContainerHealthy。
- Traffic：100%至`00030-pgg`。
- Current digest：`sha256:7301a529d18506f5f46832090421924cd7c40e2726233d0062fbc2ea1a4c8698`。
- Runtime identity：default Compute Engine service account。
- Concurrency／timeout／max scale：80／300 seconds／100。
- Service與underlying Cloud Run IAM沒有public binding，維持private。
- Runtime Secret references：database password latest、weather API key version 2、LINE access token version 1；resolved versions均Enabled，未讀取value。

部署前必須重新執行上述唯讀檢查；任一項改變需停止並重新評估。

## 5. Scheduler與真實副作用

Existing enabled jobs（Asia/Taipei）：

- `BroadcastGameReminder`：每日09:30，POST reminder route。
- `BroadcastGameCancellation`：週一至週五、週日16:30，POST cancellation route。
- `BroadcastGameInvitation`：週一至週五、週日17:30，POST invitation route。

部署本身及`GET /healthz`不發通知、不查DB、不呼叫weather；但新revision承接100% traffic後，既有Scheduler會依原排程自然呼叫business routes並可能發送真實LINE／Discord或寫入announcement timestamps。Owner必須明確接受此自然副作用。

不修改、pause、resume或人工觸發任何Scheduler job。

## 6. Build與deployment範圍

- 從exact commit `9744331`的隔離source tree建置，避免帶入任何工作文件或未追蹤檔案。
- 重建`shared_lib-0.0.1.tar.gz`並記錄hash；shared library source本次無變更。
- 只執行`game-broadcast-service` Cloud Build／Cloud Run deployment。
- 仍使用現有runtime Secret bindings及`--no-allow-unauthenticated`。
- 不修改image tagging方案、Cloud Build config、Dockerfile、IAM、Secret或env source。
- 不讀取、顯示、提交或複製Secret value。

## 7. 部署後驗證

### Control-plane

- Cloud Build SUCCESS並記錄build ID。
- 新revision Ready／Active／ContainerHealthy，100% traffic。
- 記錄new digest、revision及update time。
- Runtime identity、concurrency、timeout、max scale及Secret references未退化。
- Service與underlying IAM仍沒有public binding。
- Scheduler target／method／OIDC identity／schedule未變。

### Authenticated health smoke

- 使用具Cloud Run Invoker權限的當前部署身分，將identity token只保存在process variable／Authorization header，不輸出、不寫檔。
- 僅呼叫一次新service的`GET /healthz`。
- 必須取得HTTP 200、`application/json`、`Cache-Control: no-store`及精確payload：

```json
{"service":"game-broadcast-service","status":"ok"}
```

- 不呼叫任何POST business route，不讀application logs或production data。

## 8. Rollback

Rollback target：`game-broadcast-service-00030-pgg`。

符合任一條件時，將100% traffic切回`00030-pgg`：

- Build失敗或new revision無法Ready／ContainerHealthy。
- Private IAM、runtime identity、Secret references或resource contract退化。
- Authenticated`GET /healthz`不是預期200／JSON contract。
- Scheduler target、method、identity或schedule非預期改變。
- 無法建立commit→build→digest→revision追溯。

Rollback只切traffic，不刪除revision、不修改Scheduler／IAM／Secret。Code rollback無法撤回已發送通知或復原已寫入production data。

## 9. 明確不在範圍

- `notify-cronjob-service`或其他服務部署。
- Invitation、cancellation、reminder endpoints人工invoke。
- 真實LINE／Discord測試通知。
- Production DB讀寫或手動資料修復。
- Secret value存取／輪替、IAM或Scheduler mutation。
- Web Portal、LINE webhook、Cloud Functions deployment。

## 10. Owner exact deployment批准文字

```text
批准將commit 974433168b86e5638adce779ed8eccced0542094部署至production的game-broadcast-service，依TASK-014與deployment runbook執行build、deploy、control-plane驗證，並使用具授權身分僅呼叫一次private GET /healthz；若符合rollback trigger，批准將100% traffic切回game-broadcast-service-00030-pgg。我接受部署後既有Scheduler依原排程自然呼叫新revision並可能發送真實通知或寫入既有announcement timestamps。不批准人工呼叫invitation／cancellation／reminder routes、其他服務部署、Secret/IAM/Scheduler修改、production data操作或application log讀取。
```

## 11. 執行結果（2026-08-05）

- 隔離source：exact commit `974433168b86e5638adce779ed8eccced0542094`；未納入本機未提交文件。
- Offline驗證：game broadcast 26/26 tests通過；compile check通過；shared library重新build。
- 第一次Cloud Build `08d76d08-28bf-4e83-8ee8-a25ff904d5a6`因PowerShell substitutions quoting錯誤，在Docker build前失敗；未部署或改變traffic。
- 第二次Cloud Build `fe74ab5d-7fa8-4ff1-8220-fa914b569f63`成功；建立revision `game-broadcast-service-00031-s65`，digest `sha256:bbf30a215b895a1fd2037dc30f23915e7656c1a1d810d15af93e04a26aad8b9f`。
- 新revision Ready並曾承接100% traffic；private IAM、runtime identity、concurrency、timeout、Secret references與三個Scheduler jobs均未漂移。
- 唯一一次authenticated `GET /healthz`回傳HTTP 404，不符合第7、8節contract；未重試、未改試其他URL、未讀application logs。
- 已觸發rollback，100% traffic切回Ready的`game-broadcast-service-00030-pgg`；舊digest仍為`sha256:7301a529d18506f5f46832090421924cd7c40e2726233d0062fbc2ea1a4c8698`。
- Rollback後service維持private，三個Scheduler jobs未變。`00031-s65`保留但不承接traffic。
- 未人工呼叫任何business route；未修改Secret／IAM／Scheduler；未執行production data操作。隔離暫存與temporary env已清理。
