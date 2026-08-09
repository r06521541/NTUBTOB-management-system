# TASK-045：移除LINE webhook過時的attendance cache HTTP呼叫

## 目標

移除LINE webhook在成功寫入賽事出席回覆後，對Web Portal不存在的`/clear-cache/attendance`發出的同步HTTP呼叫。確保回覆流程不再因無timeout、必然無效的外部請求而延遲或失敗，同時以測試證明Web Portal attendance頁仍會request-time讀取最新資料。

## 已確認事實

- `shared_lib/shared_module/web_cache.py`硬編碼production Web Portal URL，並以`requests.get()`呼叫`/clear-cache/attendance`，沒有timeout。
- `functions/line_webhook_handler/webhook.py`在`GameAttendanceReply.add()`後同步呼叫該helper。
- Repository沒有`/clear-cache/attendance` route；Web Portal的blocked endpoint清單雖含`clear_attendance_cache`名稱，但沒有實際route function。
- Web Portal只對`/future-games`使用Flask cache；`/attendance`沒有cache decorator，request-time呼叫`Game.search_for_invited()`與`attendance_analyzer.get_attendance_of_game()`。
- Repository搜尋只找到LINE webhook這一個`shared_module.web_cache` caller。

## 使用者價值

- LINE出席回覆不再等待或受制於一個不存在的Web Portal endpoint。
- 降低webhook timeout、重試及重複事件造成副作用的風險。
- 保持attendance網站與LINE查詢直接反映資料庫中的最新回覆。

## 工作範圍

1. 先新增可離線重現現況的LINE webhook attendance reply測試：
   - 使用fake Flask request context／`g.user`與mock models、game、message helpers。
   - 成功的新回覆仍精確執行一次`GameAttendanceReply.add()`並加入既有LINE reply message。
   - 相同回覆、未配對、尚未完成初次互動、已過期或已取消等既有分支保持原行為。
   - 成功與所有重要分支均不得執行任何Web Portal HTTP request；測試patch `requests.get`／`requests.request`等邊界以fail-on-call證明。
   - 不傳送真實LINE／Discord、不連DB、不呼叫production。
2. 移除`webhook.py`對`shared_module.web_cache`的import與成功回覆後的呼叫。
3. 若全repository搜尋確認沒有其他caller，刪除`shared_lib/shared_module/web_cache.py`；若發現其他實際caller，停止刪除並在report列出，不擴張處理。
4. 補Web Portal離線契約，證明`/attendance`沒有response cache並在每次有效member request呼叫fresh attendance analyzer；可沿用／強化既有route tests，不為了測試建立新cache endpoint。
5. 更新LINE webhook README與相關系統文件，說明attendance reply不依賴跨服務cache invalidation。

## 非目標

- 不新增替代HTTP endpoint、timeout、retry、queue或Pub/Sub；無效呼叫應直接消失。
- 不改LINE訊息文字、reply順序、Discord late-reply規則、資料寫入方式或idempotency策略。
- 不修改schema、models、migration、Secret、IAM、Scheduler、LINE Console或deployment config。
- 不處理其他`requests`呼叫、全面重構舊webhook或擴張至其他services。
- 不push、不建立PR、不merge、不部署，不連production DB、不發真實通知。

## 工程與安全限制

- 修改前確認git status並保留既有變更。
- 所有LINE、Discord、DB與HTTP邊界均mock；測試不可發外部請求。
- 修改shared library後須重建／安裝sdist，確認刪除module不會造成artifact或direct consumer import失敗。
- 不把production URL、token、body或exception內容加入新log。
- 保持Python 3.10相容，diff聚焦。

## 驗收條件

1. Repository不再包含LINE attendance reply對Web Portal的cache invalidation HTTP呼叫。
2. 成功新回覆仍只新增既有DB record與reply message；不因移除呼叫改變late notification條件或其他分支。
3. Offline tests以fail-on-network證明attendance reply path不呼叫Web Portal或其他意外HTTP。
4. Web Portal attendance route每次有效request仍取得fresh Member、games及attendance analyzer結果，沒有新增cache。
5. `shared_module.web_cache`無caller後安全移除，重新build的shared sdist與LINE webhook imports通過。
6. LINE webhook、Web Portal受影響測試、shared library build/import、compile、Python 3.10 grammar與diff check通過。

## 驗證命令

```text
python -m unittest discover -s functions/line_webhook_handler/tests -v
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q functions/line_webhook_handler shared_lib/shared_module apps/web_portal
git diff --check
git status --short
```

另依repository既有方式重建並安裝`shared_lib-0.0.1.tar.gz`，再做LINE webhook import check與Python 3.10 AST grammar檢查。若Windows缺少Unix make/sh，使用等價Python/build命令並記錄限制，不修改Makefile。

## 主要相關檔案

- `functions/line_webhook_handler/webhook.py`
- `functions/line_webhook_handler/tests/`
- `functions/line_webhook_handler/README.md`
- `shared_lib/shared_module/web_cache.py`
- `apps/web_portal/tests/test_admin_security.py`
- 必要協作文件

## 交付

- 使用一個描述性主要commit，例如`fix(line-webhook): remove obsolete attendance cache request`。
- report與handoff併入完成commit，避免純流程commit。
- 完成後設為`ready_for_review / work`；不得push、PR、merge或deployment。

## Base commit

`bc6f08f1257fdc84aac26f683ee6a79999f71b4d`

## 部署提示

本任務若後續合併，功能變更位於LINE webhook function及shared library artifact；不需要重新部署Web Portal。任何Cloud Functions Gen2 deployment仍須另行取得exact merge commit、rollback條件與production授權。

