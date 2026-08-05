# TASK-025 Codex Report

狀態：`ready_for_review`
執行者：Codex
規格 base：`9f44165`
實際開始 HEAD：`86ce3688cbce230c5d04a4f35458dd5f4895ad1d`（包含TASK-025規劃commit）
實作 commit：`22ebe92`

## 完成內容

- 新增獨立development-only `demo_events` blueprint與虛構fixture，不載入DB model或外部來源。
- 一般活動列表支援安全類型filter；只顯示published／cancelled，draft僅幹部builder可見。
- Event detail以mobile timeline呈現交通、住宿、聚餐及三場比賽，清楚標示`league_imported`唯讀fixture與`manual`來源。
- Demo officer builder支援友誼賽／聚餐／週末移地三種模板及空白建立、Event欄位編輯、Activity新增／編輯／刪除／上下排序、預覽、發布／取消／回草稿。
- Event狀態轉換只改session，頁面明示不發LINE；正式角色、第二人覆核、同步與去重保持待決策。
- 一般成員可回覆Event整體狀態、套用全部Activity後逐項覆寫，Activity另支援`not_applicable`；Dashboard顯示published活動待辦。
- Event上限5、每個Event Activity上限12；server產生`event-demo-*`／`activity-demo-*` IDs，文字、日期、時間、類型、來源、狀態及action均具限制／allowlist。
- 所有管理POST具demo gate、登入、獨立demo officer guard及CSRF；非officer GET／POST皆403且零session mutation。
- HTML-like輸入由Jinja autoescape；所有session內容皆為JSON-compatible primitives。
- README補充完整原型範圍、啟動方式與正式版未決事項。

## 驗證

測試runtime：bundled Python 3.12.13；本機Python 3.10 launcher仍失效，沒有本機3.10實跑證據。

```text
python-runtime -m unittest discover -s apps/web_portal/tests -v
44 tests: OK，2 skipped

python-runtime -m compileall -q apps/web_portal
passed

git diff --check
passed
```

兩項skip為Windows環境缺`make`／`sh`的既有deployment executable coverage。新增11項Event測試涵蓋gate／匿名、officer guard、四種建立方式、Event／Activity validation、CRUD排序、跨Event guard、數量上限、唯讀league fixture、狀態轉換、CSRF、HTML escaping、兩層出席／隔離、完整建立發布回覆流程，以及model／HTTP不可呼叫。

## Prototype、限制與風險

- 全部Event、Activity、狀態與回覆只存在signed Flask session；cookie容量仍是原型規模限制，因此硬性限制5×12及文字長度。
- 聯盟資料是repository-local fixture，不呼叫crawler，不代表同步／去重設計已完成。
- Demo officer role不是正式RBAC；沒有第二人覆核、audit persistence或通知。
- 沒有瀏覽器自動化視覺實測；已提供375px單欄CSS contracts，長時間軸與表單仍待Work／Owner主觀瀏覽。
- `app.py`僅註冊新的demo blueprint；沒有改動既有production route實作或認證行為。
- 未修改shared_lib、schema、migration、deployment、Secret、IAM或其他服務；未連Supabase／production DB，未呼叫外部API或通知，未deploy／push／建立PR。

## 變更檔案

- `apps/web_portal/app.py`
- `apps/web_portal/README.md`
- `apps/web_portal/demo_data.py`
- `apps/web_portal/demo_portal.py`
- `apps/web_portal/demo_event_data.py`
- `apps/web_portal/demo_events.py`
- `apps/web_portal/static/events.css`
- `apps/web_portal/templates/demo/base.html`
- `apps/web_portal/templates/demo/dashboard.html`
- `apps/web_portal/templates/demo/officer.html`
- `apps/web_portal/templates/demo/events/builder.html`
- `apps/web_portal/templates/demo/events/detail.html`
- `apps/web_portal/templates/demo/events/list.html`
- `apps/web_portal/templates/demo/events/officer.html`
- `apps/web_portal/tests/test_demo_events.py`
- `docs/coordination/reports/TASK-025-CODEX.md`
- `docs/coordination/HANDOFF.yaml`

任務開始時工作樹乾淨；無既有未提交變更混入。沒有migration、環境變數或deployment設定變更，也沒有需要Owner立即決策的執行阻礙。
