# TASK-046：建立attendance延遲分段量測基線

## 目標

在不改cache、雲端容量或資料行為的前提下，為Web Portal `/attendance`建立安全、可測試的分段耗時診斷，區分Member／DB首次連線、賽事查詢、逐場attendance分析、template render與整體request耗時，作為後續判斷Cloud Run cold start、Supabase pooling、query/index或共享cache的依據。

## 背景與已確認事實

- Owner回想原cache動機是首次資料取得約需10秒，懷疑GCP cold start。
- 依目前repository，`/attendance`由Cloud Run Web Portal直接呼叫`Member.search_by_id()`、`Game.search_for_invited()`與`attendance_analyzer.get_attendance_of_game()`；request path沒有呼叫Cloud Functions。
- LINE webhook是Cloud Functions Gen2，但其attendance reply為寫入流程，不負責Web Portal頁面讀取。
- `/attendance`目前不使用response cache；TASK-045已移除無效的跨服務cache invalidation HTTP呼叫。
- 尚無分段證據能判定10秒來自container startup、首次DB connection、query、每場analyzer或render，因此不得先選Redis、minimum instances或query重寫。

## 工作範圍

1. 建立小型、可注入clock的attendance timing helper：
   - 使用monotonic／`perf_counter`類型時鐘，不使用wall-clock計算duration。
   - 固定stage名稱，例如`member_lookup`、`games_query`、`attendance_analysis`、`render`與`total`。
   - duration正規化為非負整數milliseconds並設定合理上限；異常／非數值clock結果不得讓request失敗或洩漏內部資料。
2. 在`/attendance`最小插入分段量測：
   - 保持現有query次數、順序、fail-closed Member處理、template內容與HTTP status。
   - `attendance_analysis`可涵蓋所有game analyzer呼叫總和，不記錄game ID、Member ID、姓名、reply內容或逐場明細。
   - render完成後以best-effort方式輸出單一固定格式診斷，例如：
     `attendance_timing member_lookup_ms=... games_query_ms=... analysis_ms=... render_ms=... total_ms=...`
   - logging故障不得改變response；不得使用同一故障logger再記錄例外。
3. 建立冷／暖判讀所需的最小process資訊：
   - 可用固定`request_phase=first|subsequent`表示該process的第一次有效attendance request，必須thread-safe或採不影響正確性的保守設計。
   - 不記錄instance ID、trace ID、IP、User-Agent、URL/query、cookie、session或identity。
   - 若安全且簡單無法保證，可省略phase，改以Cloud Run revision request latency與stage總和離線比對；在report說明限制。
4. 離線測試：
   - 注入deterministic clock，驗證各stage與total的計算／輸出。
   - sentinel證明log不含Member、game、URL/query、cookie、OAuth、DB DSN、Secret或exception內容。
   - member不存在、DB/model exception及logging failure不改變既有HTTP／exception contract。
   - timing不得增加DB/model/analyzer呼叫次數。
   - Demo與其他routes不輸出attendance timing。
5. 更新README與效能診斷說明：
   - 說明目前runtime path不經Cloud Function。
   - 定義未來production量測需Owner另行批准部署與固定欄位log query。
   - 定義判讀矩陣，但不在本任務修改cloud config。

## 建議判讀矩陣

| 證據 | 優先策略 |
| --- | --- |
| 首次request整體慢，但app stages總和低 | 評估Cloud Run minimum instances／startup CPU／import-time縮減 |
| `member_lookup`首次特別慢 | 檢查Supabase connection pooler、SQLAlchemy engine reuse與連線初始化 |
| `games_query`穩定偏慢 | 檢查query plan、欄位與index |
| `attendance_analysis`隨game數增加明顯 | 檢查N+1、批次query或預先聚合 |
| DB/query已優化且讀取壓力仍高 | 才評估共享Redis短TTL；不使用instance-local cache作一致性來源 |

## 非目標

- 不設定Cloud Run minimum instances、CPU、concurrency或scaling。
- 不修改Supabase連線、pooling、query、index、schema或migration。
- 不新增Redis／Memorystore、cache endpoint、Pub/Sub、queue或response cache。
- 不改LINE webhook、shared library、attendance UI、登入、權限或資料結果。
- 不讀production logs、不連production DB、不執行load test或外部HTTP。
- 不push、不建立PR、不merge、不部署；後續另由Owner批准。

## 安全與工程限制

- 所有log keys與stage names為source-defined allowlist；不得把raw path、exception、model值或request資料拼入log。
- timing helper與logging皆為best-effort observability，不得成為availability dependency。
- 不使用高基數labels或每個game一筆log；一次成功attendance response最多一筆timing event。
- Python 3.10相容，不新增dependency，保持diff聚焦。

## 驗收條件

1. `/attendance`成功request產生一筆固定欄位、無個資的分段timing診斷。
2. deterministic tests證明stage與total計算正確，且不增加Member／Game／analyzer呼叫。
3. failure paths與logging failure保持原有response／exception行為。
4. sentinel測試證明log不含URL/query、cookie、OAuth、identity、game/member資料、DB資訊、Secret或exception內容。
5. Demo與非attendance routes不產生該診斷。
6. Web Portal完整測試、compile、Python 3.10 grammar與diff check通過。

## 驗證命令

```text
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q apps/web_portal
git diff --check
git status --short
```

## 主要相關檔案

- `apps/web_portal/app.py`
- 可新增`apps/web_portal/performance_diagnostics.py`
- `apps/web_portal/tests/`
- `apps/web_portal/README.md`
- 必要協作文件

## 交付

- 使用一個描述性主要commit，例如`perf(web-portal): measure attendance request stages safely`。
- report與handoff併入完成commit，避免純流程commit。
- 完成後設為`ready_for_review / work`；不得push、PR、merge或deployment。

## Base commit

`0009b497125eacba66e586e85494f307c198a6db`

## 後續

TASK-046只建立量測能力。若未來部署並取得Owner實測，Work再依固定timing fields提出單一優化任務；不得一次同時啟用minimum instances、改pooling與新增cache。

