# TASK-015 Work Review

結論：`accepted_with_bounded_diagnosis`
日期：2026-08-05
Reviewer：Work
Base commit：`974433168b86e5638adce779ed8eccced0542094`

## 管理結論

TASK-014的404不是由缺少Flask `/healthz` route、錯誤build source或image漏檔造成。精確時間窗內沒有對應Cloud Run request log，表示request沒有到達revision container；問題層級已縮小至Cloud Run frontend／入口或其前置policy。

目前不足以在不增加production evidence的前提下，進一步斷定是URL／URL alias、VPC Service Controls或其他frontend policy。TASK-015依安全停止條件結束，沒有重送production request。

## 已確認事實

- Cloud Build `fe74ab5d-7fa8-4ff1-8220-fa914b569f63`為SUCCESS；source generation與revision／Artifact Registry digest可核對。
- Revision `game-broadcast-service-00031-s65` Ready，image digest為`sha256:bbf30a215b895a1fd2037dc30f23915e7656c1a1d810d15af93e04a26aad8b9f`。
- Production traffic維持`game-broadcast-service-00030-pgg` 100%。
- Service ingress為`all`，default URL未disabled，沒有custom audience。
- Build source的五個關鍵檔案與target commit Git blobs完全一致。
- Deployed image內的`app.py`、`health.py`及Dockerfile與target commit Git blobs完全一致，health registration與route存在。
- TASK-014呼叫account具有project `roles/owner`。
- 精確Cloud Run request log query回傳0筆matching records。
- 精確Cloud Audit policy query亦回傳0筆：時間窗2026-08-05 03:25–03:45 UTC、`cloudaudit.googleapis.com/policy`、method `run.googleapis.com/HttpIngress`且限定`game-broadcast-service`。

## 已排除

- Build使用錯誤target source。
- Docker image漏掉`health.py`或route registration。
- Revision引用舊image digest。
- Service ingress不是`all`或default URL被停用。
- 呼叫者明顯缺少Cloud Run invoke permission。
- 404由Flask route不存在直接產生。

## 尚未確認

- TASK-014使用的`status.url`與Cloud Run部署輸出的另一個URL形式是否在當下具有不同routing行為。
- 是否存在VPC Service Controls `HttpIngress` policy denial。
- 其他Cloud Run frontend policy是否產生沒有container request log的404。

後續Cloud Audit查詢沒有找到可記錄的`HttpIngress` denial，因此VPC Service Controls由「待查主要候選」降為「沒有現有證據支持、但仍不能完全排除」。URL／URL alias routing仍是最值得以單次受控request驗證的方向。

## 本機image驗證限制與額外發現

實際production digest image在`network none`及假環境值下，會在Flask開始listen前因`LineBotAnnouncementHelper()`的import-time database query失敗。這不是TASK-014 production 404的原因，因`00031-s65`線上Ready；但代表目前health endpoint只能證明已成功啟動的process，無法提供不依賴DB的startup／liveness probe。此設計風險適合另立任務，不應混入404診斷修正。

## 安全與清理

- 未再次呼叫production endpoint，未讀application stdout/stderr或payload。
- 未部署、切traffic或修改revision／IAM／Secret／Scheduler／network。
- 未讀寫production DB，未發送LINE／Discord通知。
- 暫時containers、production digest image及diagnostic directory均已移除。
- 本機Docker新增Artifact Registry的gcloud credential helper設定；它不保存獨立token，並使用既有gcloud登入身分。

## 下一個最小證據

Cloud Audit policy logs已完成精確查詢且為0筆。下一個最小證據需另行批准一次受控production request：優先以Google官方建議的`gcloud run services proxy`，或明確canonical service URL做單次authenticated `GET /healthz`。該授權不得包含traffic、deploy、IAM或其他mutation。
