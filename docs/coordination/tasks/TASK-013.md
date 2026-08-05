# TASK-013：排程服務無副作用 Health Checks

狀態：`ready_for_codex`
優先級：P1
規劃者：Work
執行者：Codex
`base_commit`：`3389f96d6221f6ca0c566e6c74bf516012d83a83`
Branch：`codex/add-scheduled-service-health-checks`

## 1. 任務目標

為 production中兩個private Cloud Run排程服務建立可安全呼叫的process-level health endpoint，使未來部署後可以驗證Flask app與route正常，而不會發送LINE／Discord、查詢或寫入DB、呼叫weather或觸發任何排程業務行為。

目標服務：

- `apps/game_broadcast_service`
- `apps/notify_cronjob_service`

## 2. 背景與已確認現況

- 兩個服務目前所有業務routes都是POST且具有通知、DB或外部服務副作用。
- TASK-008／009部署後只能查revision health、IAM與control-plane metadata，無法安全做application-level smoke test。
- 兩個Cloud Build deployment均使用`--no-allow-unauthenticated`；服務必須維持private。
- 服務module import時會建立Discord／LINE helper；本任務不是全面改寫初始化架構，但health request本身不得呼叫這些helpers。
- 現有deployment contract tests已保護Secret bindings、private flag及build context。
- Deployment runbook已將「建立不會發通知／寫資料的health check」列為P1缺口。

## 3. 核准與PR工作包

Owner已批准TASK-013及標準PR工作包：允許建立branch、描述性commits、push、Draft PR、CI查驗及同一PR內的Codex report／Work review更新。

不包含merge、deployment、production endpoint invocation、Secret／IAM／Scheduler操作、正式通知或production data存取。

## 4. 工作範圍

### 4.1 Endpoint contract

兩個服務各新增：

```text
GET /healthz
```

必要行為：

- 回傳HTTP 200及`application/json`。
- 固定且最小response：`status`與`service`；service分別能辨識兩個服務。
- 加入`Cache-Control: no-store`，避免健康結果被中介cache誤用。
- 不回傳Git SHA、hostname、環境變數、Secret、dependency狀態、exception或其他內部metadata。
- 不查DB、不呼叫LINE／Discord／weather／crawler，不修改任何state。
- 不把business dependencies納入readiness判斷；這是process-level liveness/smoke endpoint。
- POST `/healthz`不得執行，應由Flask回405。

若能以一個小型共用helper減少兩個app重複，helper應放在各app可直接載入且不引入shared library rebuild的位置；禁止為兩行response修改`shared_lib`。

### 4.2 Tests

新增可離線執行的route tests。測試必須在不連DB／外部API的情況載入各服務，並將下列邊界替換成「一旦呼叫即失敗」的fake/mock：

- `Game`與attendance analyzer。
- LINE Messaging broadcast／announcement helper。
- Discord notify helper。
- Crawler client及weather-related helper（若該service import graph存在）。

至少驗證：

- 兩個`GET /healthz`皆為200 JSON，payload精確符合contract。
- `Content-Type`與`Cache-Control: no-store`。
- POST為405。
- 連續呼叫結果穩定且沒有dependency mock被呼叫。
- 既有business route methods／paths沒有被改名或移除。
- Cloud Build仍為`--no-allow-unauthenticated`。

測試可採isolated import、module stubs或app factory的最小拆分；不得為測試降低production auth或改變業務route行為。

### 4.3 Documentation

- 更新兩個service README；若目前不存在，建立精簡README，說明`/healthz`是private、無dependency檢查、不能代表通知／DB整合健康。
- 更新`docs/operations/DEPLOYMENT_RUNBOOK.md`：部署後可使用具授權身分的GET health check，但production invocation仍須另行exact deployment／verification授權；不得把此PR授權解讀為可呼叫production。
- 完成`docs/coordination/reports/TASK-013-CODEX.md`並更新HANDOFF。

## 5. 非目標

- 不部署或呼叫production／staging endpoint。
- 不新增公開health endpoint或修改Cloud Run IAM。
- 不檢查DB、LINE、Discord、weather、crawler或Secret Manager connectivity。
- 不修改Scheduler、通知內容、通知時機、business routes或資料模型。
- 不修改`shared_lib`、schema、migration、Docker runtime或Cloud Build部署參數。
- 不建立metrics、alerting、uptime check或完整observability平台。
- 不順手重構helper初始化、error handling或logging。

## 6. 驗收條件

- [ ] 兩個服務都有符合固定contract的`GET /healthz`。
- [ ] Health request可在dependency全部設為fail-on-call時離線成功。
- [ ] POST `/healthz`為405，既有business route contract不變。
- [ ] Response不含Secret、environment、host或dependency details。
- [ ] 兩個Cloud Run deployment contract仍維持private。
- [ ] README與deployment runbook清楚說明liveness限制與production授權邊界。
- [ ] 所有既有及新增測試通過，Python 3.10 CI成功。
- [ ] 沒有shared_lib、schema、deployment config或其他service diff。

## 7. 必要驗證

```text
python -m unittest discover -s apps/game_broadcast_service/tests -v
python -m unittest discover -s apps/notify_cronjob_service/tests -v
python -m compileall -q apps/game_broadcast_service apps/notify_cronjob_service
git diff --check
git status --short
```

Codex在PR工作包內還需確認GitHub Actions的Python 3.10 job；本機若非3.10需明確記錄實際版本。

## 8. 安全停止條件

遇到下列狀況立即停止並交回Owner／Work：

- 需要Secret value、production credential或`envs/**/.env.yaml`內容。
- 需要呼叫production service才能完成測試。
- Health endpoint必須公開或必須修改IAM／Scheduler才能使用。
- 需要修改schema、shared library或業務通知行為。
- 測試意外發出network request、通知或DB連線。

## 9. 風險與假設

- Health 200只代表container內的Flask process可處理route，不代表DB、LINE或其他dependency可用。
- 由於服務private，未來production smoke需OIDC／authorized identity；實際呼叫仍須部署任務明確授權。
- Module import仍可能建立SDK helper objects；本任務只保證health request不呼叫副作用，若constructor本身有network side effect則必須以證據停止並回報，不得大幅重構。
