# TASK-015：診斷 Game Broadcast Health Check 404

狀態：`completed`（frontend layer identified）
優先級：P1
規劃者：Work
執行者：Work
Base commit：`974433168b86e5638adce779ed8eccced0542094`

## 1. 任務目標

在不重新部署、不切換production traffic且不再次呼叫production endpoint的前提下，判定TASK-014唯一一次authenticated `GET /healthz`回傳HTTP 404的層級與最可能根因，並提出一個最小修正或最小補充驗證方案。

本任務只做診斷與文件，不修改application code。

## 2. 背景與已確認事實

- TASK-013 source與actual-app offline tests均確認`game-broadcast-service`註冊`GET /healthz`。
- Target commit `9744331`的`app.py`包含`app.register_blueprint(create_health_blueprint())`，Dockerfile使用`COPY . .`。
- Cloud Build `fe74ab5d-7fa8-4ff1-8220-fa914b569f63`成功。
- Revision `game-broadcast-service-00031-s65` Ready，image digest為`sha256:bbf30a215b895a1fd2037dc30f23915e7656c1a1d810d15af93e04a26aad8b9f`。
- 新revision曾承接100% traffic；private IAM、runtime identity、Secret references與Scheduler contract沒有退化。
- 對service `status.url`的唯一一次authenticated `GET /healthz`回傳Google樣式HTTP 404。
- 已依TASK-014 rollback trigger將100% traffic切回Ready的`game-broadcast-service-00030-pgg`；`00031-s65`保留為0% traffic。
- TASK-014未讀application logs，因此目前無法確認該request是否到達container。

## 3. 推論與待確認假設

### 合理推論

- Source route registration與offline behavior已有強證據，優先檢查build provenance、實際image內容及Cloud Run frontend routing，比直接修改Flask route更合理。
- Google Cloud官方文件指出，Cloud Run 404可能來自錯誤URL／application，也可能在request未到container時由ingress、disabled default URL或VPC Service Controls產生。
- Private Cloud Run的ID token audience應對應receiving service的`*.run.app` URL或已設定custom audience；TASK-014沒有輸出token claims，因此audience仍待確認。

### 尚未確認

- Build實際上傳的source archive是否包含預期`health.py`與registration。
- Digest `bbf30a...`的container在完全相同image下是否能於本機回傳`/healthz` 200。
- Service是否存在ingress、default URL、custom audience、URL alias或其他routing設定差異。
- TASK-014的404是否出現在Cloud Run request log；若不存在，代表request可能未到container。
- 404是否由Cloud Run frontend、IAM token audience、URL alias或application routing產生。

不得在沒有證據時把其中任一假設宣稱為根本原因。

## 4. 工作範圍

### Phase A：不接觸production request／logs的唯讀診斷

1. 重新確認Git target、working tree與TASK-014 evidence，保留既有未提交文件。
2. 唯讀查詢Cloud Build metadata／provenance、revision image digest與service metadata；不讀build中的Secret或環境值。
3. 核對service及revision的：
   - canonical／reported URLs與annotations。
   - ingress、default URL、custom audiences、traffic及private IAM。
   - container command／args、port、image digest及runtime identity。
4. 以digest唯讀下載`00031-s65`使用的container image；不得重新tag或push。
5. 優先以image filesystem inspection確認`app.py`、`health.py`及registration存在；只記錄必要hash／path，不輸出設定值。
6. 若本機Docker可用，以明顯假值、`--network none`及非production port啟動該image：
   - 只呼叫本機`GET /healthz`與本機`POST /healthz`。
   - 驗證200 JSON／`no-store`及POST 405。
   - 不掛載或讀取`envs/**/.env.yaml`，不連DB、LINE、Discord、crawler或weather。
7. 若Docker不可用，以image export／filesystem inspection及exact source offline tests作替代，明確標記未完成runtime-equivalent驗證。

### Phase B：極窄範圍production request log metadata

只有Owner明確批准後才執行：

- 查詢TASK-014那一次404時間附近、revision `00031-s65`、path `/healthz`、status 404的Cloud Run **request log metadata**。
- 只允許讀取timestamp、revision、request method/path、status、latency、user-agent及trace/request識別資訊。
- 不讀application stdout/stderr、request／response body、Authorization header、token、env、Secret或production data。
- 目的僅為判定request是否到達container，以及404由frontend或application層產生。

## 5. 明確非目標

- 不再次呼叫任何production URL，包括`/healthz`。
- 不呼叫invitation、cancellation或reminder routes。
- 不部署、不build新revision、不切traffic、不建立revision tag。
- 不修改code、tests、Dockerfile、Cloud Build、IAM、Secret、Scheduler或network policy。
- 不讀Secret value、application stdout/stderr、production DB或業務資料。
- 不發送LINE／Discord訊息，不人工觸發Scheduler。
- 不刪除`00031-s65`或任何image／revision。

若Phase A與B仍無法定案，必須停止並向Owner提出下一個精確授權，不得自行重送production request或修改設定。

## 6. 診斷判定矩陣

| 證據 | 判定方向 | 下一步 |
| --- | --- | --- |
| Deployed image缺少route檔案或registration | Build source／artifact provenance問題 | 提出build packaging修正任務，不直接改production。 |
| Deployed image本機斷網執行仍回404 | Image內application routing問題 | 建立最小code／packaging fix與回歸測試任務。 |
| Deployed image本機回200，production 404沒有request log | Cloud Run frontend、URL、ingress或audience方向 | 提出一次精確canonical URL／audience驗證工作包。 |
| Deployed image本機回200，production 404有container request log | Runtime environment或application request routing差異 | 根據request metadata提出最小重現；需要stdout/stderr時另請批准。 |
| 證據矛盾或不足 | 根因未定 | 停止，不部署、不invoke；列出下一個最小證據需求。 |

## 7. 驗收條件

- 建立commit→Cloud Build→source／image digest→revision的可核對鏈。
- 明確記錄deployed image是否包含health route及registration。
- 若環境允許，使用production digest的image完成本機斷網health contract驗證；否則記錄替代證據與限制。
- 記錄service URL／ingress／default URL／custom audience相關metadata，不顯示credential。
- 若Phase B獲批，明確判定那次404是否有對應container request log。
- 最終結論必須區分：已確認根因、最可能原因、已排除原因與仍未知事項。
- 產出`docs/coordination/reviews/TASK-015-WORK.md`，不得把推論寫成事實。
- `git diff --check`通過；不產生未清理的image export、container、token或temporary credential file。

## 8. 安全與停止條件

- 任何操作若會產生production request、變更traffic／revision／IAM／Secret／Scheduler／network，立即停止並回Owner。
- 不輸出或保存identity token；本任務既定範圍不需要產生token。
- Image本機啟動必須`--network none`且只用假環境值；若無法保證斷網，不啟動。
- 發現image或build artifact包含Secret時立即停止，不輸出內容，只回報暴露類型與位置。
- 發現production正在由`00031-s65`承接traffic或其他control-plane漂移時立即停止。

## 9. 相關資源

- `apps/game_broadcast_service/app.py`
- `apps/game_broadcast_service/health.py`
- `apps/game_broadcast_service/Dockerfile`
- `apps/game_broadcast_service/cloudbuild.yaml`
- `apps/game_broadcast_service/tests/test_health.py`
- `docs/coordination/tasks/TASK-014.md`
- `docs/coordination/reviews/TASK-014-WORK.md`
- `docs/operations/deployments/GAME_BROADCAST_HEALTH_9744331.md`
- Google Cloud官方：[service-to-service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service)、[Cloud Run troubleshooting](https://docs.cloud.google.com/run/docs/troubleshooting)、[managing services](https://docs.cloud.google.com/run/docs/managing/services)。

## 10. Owner決策與建議批准文字

Owner已於2026-08-05批准下列Phase A與極窄Phase B範圍；未批准任何production request或mutation。

建議一次批准Phase A與極窄Phase B：

```text
批准依TASK-015執行game-broadcast-service health 404的唯讀診斷，包括Cloud Run／Cloud Build／Artifact Registry metadata與provenance查詢、以digest唯讀下載revision 00031-s65的image、使用假環境值及network none做本機health驗證，以及只讀取TASK-014該次404附近的Cloud Run request log metadata。不得再次呼叫production endpoint、讀application stdout/stderr或payload、修改traffic／revision／IAM／Secret／Scheduler／network、部署、讀寫production data或發送通知；若仍無法定案，停止並回報下一個最小證據需求。
```

## 11. 執行結果（2026-08-05）

- Cloud Build、Cloud Run與Artifact Registry metadata建立了build `fe74ab5d`→digest `bbf30a...`→revision `00031-s65`的追溯鏈。
- Production仍由Ready的`00030-pgg`承接100% traffic；`00031-s65`為0% traffic。
- `00031-s65` ingress為`all`；default URL未disabled；沒有custom audience；container port為8080。
- Build source archive中的`app.py`、`health.py`、Dockerfile、`cloudbuild.yaml`及`.dockerignore`與target commit Git blobs完全一致。
- 實際production digest image內的`app.py`、`health.py`與Dockerfile亦與target commit Git blobs完全一致；`/healthz` registration及route存在。
- 本機`network none` container無法完成runtime-equivalent health check：application在Flask listen前由`LineBotAnnouncementHelper()`執行import-time database query，因假本機DB不可連而exit 1。未連production DB或外部服務。
- TASK-014使用的account在project層具有`roles/owner`；Invoker權限不足不是主要嫌疑。
- 精確查詢2026-08-05 03:25–03:45 UTC、revision `00031-s65`、GET `/healthz`、status 404的Cloud Run request logs，結果為0筆。
- 因該次404沒有到達container request log，已確認404發生於Cloud Run frontend／container之前；已排除錯誤source、image漏檔及Flask route不存在。
- 現有授權不能再區分錯誤URL／URL alias、VPC Service Controls或其他frontend policy。依停止條件未重送production request、未讀Cloud Audit policy logs。
- Owner後續批准由唯讀子任務查詢2026-08-05 03:25–03:45 UTC、限定本服務與`run.googleapis.com/HttpIngress`的Cloud Audit policy metadata；精確query成功但結果為0筆。
- 因此目前沒有audit evidence支持該次404由可記錄的`HttpIngress` policy denial解釋；0筆仍不能證明完全不存在VPC Service Controls或其他frontend policy，也不能確認URL routing根因。
- 暫時containers、下載image、build archive與抽取檔案均已清除。為下載private image，本機Docker設定新增`asia-east1-docker.pkg.dev`的gcloud credential helper；沒有輸出或保存token。
