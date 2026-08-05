# TASK-016：移除排程服務 Import-time DB與通知副作用

狀態：`awaiting_owner_approval`
優先級：P1
規劃者：Work
執行者：Codex
Base commit：`974433168b86e5638adce779ed8eccced0542094`

## 1. 任務目標

讓`game-broadcast-service`與`notify-cronjob-service`在application import／Flask startup／`GET /healthz`期間不建立`LineBotAnnouncementHelper`、不查詢LINE groups資料表，也不發送通知；只有真正執行既有announcement業務流程時才延遲建立helper。

同時移除`apps/notify_cronjob_service/__init__.py`目前在package import時直接`announce('Hi')`的真實通知風險。

## 2. 背景與已確認事實

- `LineBotAnnouncementHelper.__init__()`會立即呼叫`LineGroup.search_groups_to_broadcast()`。
- 兩個service的`app.py`均在module top level執行`LineBotAnnouncementHelper()`，因此process startup依賴DB。
- TASK-015使用production digest image及`network none`驗證時，container在Flask listen前因上述DB query失敗而exit 1。
- `apps/notify_cronjob_service/__init__.py`是tracked file，module top level建立helper並執行`helper.announce('Hi')`；目前Docker以`python app.py`啟動，repository亦未找到caller，但任何未來package import都可能觸發DB與真實LINE副作用。
- 現有TASK-013 health tests將helper method設為fail-on-call，卻沒有讓helper constructor fail，因此未捕捉import-time DB query。

## 3. 使用者價值

- DB暫時不可用時，container仍可啟動並提供process／route liveness health。
- 避免單純import notify package就發送`Hi`或查production DB。
- 讓health check的「side-effect-free」契約涵蓋application startup，而不只涵蓋route handler。

## 4. 工作範圍

1. 修改兩個service的`app.py`：
   - 移除module-level `LineBotAnnouncementHelper()` construction。
   - 建立最小lazy cached getter，第一次真正呼叫既有`announce(message)`時才建立helper。
   - 同一process後續announcement沿用同一helper，保留既有groups snapshot／helper reuse語意。
2. 清理`apps/notify_cronjob_service/__init__.py`：
   - 移除module import時建立helper與`announce('Hi')`。
   - Package import不得做DB、LINE、Discord、crawler、weather或其他外部副作用。
3. 強化兩個service的actual-app health tests：
   - `LineBotAnnouncementHelper` constructor設為fail-on-call時，app import與連續health calls仍成功。
   - Health GET維持200 JSON／`no-store`，POST維持405。
   - 既有business route path／methods不變。
4. 新增lazy helper行為測試：
   - Application import不建立helper。
   - 第一次受控呼叫`announce()`才建立helper。
   - 同一app module連續呼叫只建立一次helper，訊息仍原樣交給helper。
5. 新增notify package import回歸測試，證明`__init__.py`沒有建立helper或發通知。

## 5. 設計限制

- 優先在兩個service app內做小型lazy initialization，不修改`shared_lib`的公開介面。
- 不改announcement message、recipient selection、LINE group query、business route順序、HTTP response或Scheduler contract。
- 不為health route新增DB connectivity check；`/healthz`仍只代表process與route可服務。
- Lazy cache需保持Python 3.10相容，不新增dependency。
- 不順手重構整個`app.py`或通知架構。

## 6. 明確非目標

- 不處理TASK-014的Cloud Run URL／frontend 404；該問題有獨立證據與授權門。
- 不部署、不呼叫production endpoint、不操作traffic。
- 不發送LINE／Discord通知，不連production DB、crawler或weather。
- 不修改schema、migration、Secret、IAM、Scheduler、Cloud Build、Dockerfile或environment files。
- 不修改notification recipients、排程時間、重試或idempotency規則。

## 7. 驗收條件

- 兩個service actual app可在`LineBotAnnouncementHelper()` constructor為fail-on-call時完成import及health GET。
- Health route contract與business route path／methods全部維持。
- 只有呼叫`announce(message)`才初始化helper；同一module重複呼叫不重建helper。
- `apps.notify_cronjob_service` package import不建立helper、不查DB、不發通知。
- 所有測試完全離線，外部依賴使用mock／stub。
- Python 3.10 CI通過。
- `git diff --check`與compile check通過。
- 沒有shared library、schema、deployment config或其他服務的無關diff。

## 8. 驗證命令

```text
python -m unittest discover -s apps/game_broadcast_service/tests -v
python -m unittest discover -s apps/notify_cronjob_service/tests -v
python -m compileall -q apps/game_broadcast_service apps/notify_cronjob_service
git diff --check
git status --short
```

如建立PR，必須查驗GitHub Actions實際使用Python 3.10並成功，不以local Python 3.12取代。

## 9. 風險與假設

- Lazy helper把首次LINE group DB query從process startup移到第一次announcement；若當時DB失敗，錯誤會發生在business request。Codex不得吞掉例外或改變既有route error handling。
- Helper目前快取LINE groups至process生命週期；本任務要求維持此語意，不改成每次announcement重查。
- `notify_cronjob_service/__init__.py`目前沒有已知caller是confirmed repository fact，不代表外部工具永遠不會import；移除副作用仍是安全修正。

## 10. 相關檔案

- `apps/game_broadcast_service/app.py`
- `apps/game_broadcast_service/tests/test_health.py`
- `apps/notify_cronjob_service/app.py`
- `apps/notify_cronjob_service/__init__.py`
- `apps/notify_cronjob_service/tests/test_health.py`
- 必要時新增相鄰test file；不修改`shared_lib`。

## 11. Owner決策

Owner已批准TASK-016實作與PR工作包，授權branch、描述性commit、push、Draft PR、CI查驗及同一PR內的報告／驗收文件更新；merge仍需Owner最終批准。

建議批准文字：

```text
同意TASK-016「移除排程服務import-time DB與通知副作用」，並批准PR工作包。不得部署、呼叫production、連production DB、發送通知、修改shared_lib／schema／Secret／IAM／Scheduler／deployment config或擴張至其他服務。
```
