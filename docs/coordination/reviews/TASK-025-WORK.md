# TASK-025 Work Review

驗收日期：2026-08-05
驗收者：Work
結論：`accepted`（mobile UAT補正後）

## 驗收範圍

- Branch：`main`
- Task planning：`86ce3688cbce230c5d04a4f35458dd5f4895ad1d`
- Implementation：`22ebe92`
- Report head：`b9f9633`
- 驗收開始時working tree：clean

## 驗收結果

- Event／Activity資料只存在Flask session，使用JSON-compatible primitives，未接models或DB。
- 一般活動列表只顯示published／cancelled；draft只在officer builder可見。
- Builder具友誼賽、聚餐、週末移地與空白模板，並支援Event編輯、Activity新增／編輯／刪除／排序。
- 週末fixture包含交通、住宿、聚餐及三場比賽；活動詳情以mobile timeline呈現。
- `league_imported` fixture欄位由server覆蓋client payload，既有匯入activity不可從manual edit route修改；manual games另有對手與主客場。
- Demo officer guard獨立於production admin security；非officer GET／POST皆403且測試證明零session mutation。
- Event draft／published／cancelled狀態轉換具CSRF與allowlist，UI明示不發LINE通知。
- Event整體與Activity個別出席、套用全部及逐項override均已完成，跨Event狀態隔離。
- Event 5個、Activity 12個及文字／日期／時間限制均fail closed；server產生demo IDs。
- HTML-like輸入由Jinja escape，未知filter／ID／action安全拒絕。
- `app.py`只有新增development demo blueprint註冊，未改既有production route實作或登入安全行為。

## Work實跑證據

Runtime：bundled Python 3.12.13。

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 44 tests: OK (skipped=2)

python -m compileall -q apps/web_portal
passed

git diff --check
passed
```

兩項skip是Windows環境缺`make`／`sh`的既有deployment executable coverage，與Event demo行為無關。

## 安全與範圍確認

- 未修改shared_lib、schema、migration或deployment設定。
- 未連Supabase／production DB，未呼叫crawler、LINE、Discord、calendar、map或其他外部服務。
- 未操作Secret、IAM、Cloud Run、Scheduler，未發通知。
- 未push、建立PR或部署。
- TASK-023的Web Portal runtime Secret blockers仍存在，本prototype不可據此部署。

## 已知限制與非阻擋建議

- 尚無Python 3.10執行證據；本機launcher失效。
- 尚未完成375px／desktop瀏覽器實際視覺驗收；目前只有responsive CSS與HTML contracts。
- 正式版仍需決定RBAC、第二人覆核、Event／Activity schema、league同步／去重、通知與audit。
- Session硬性限制降低cookie膨脹，但本prototype不代表正式資料容量或concurrency設計。
- Activity日期目前通過ISO格式驗證，但正式產品應決定是否強制落在Event起訖日期內。

## 結論

程式與離線測試初驗曾判定TASK-025在批准的local prototype範圍內完成；Owner後續實際以手機版瀏覽，發現幹部管理介面沒有可見入口，因此撤回accepted並改為`changes_requested`。

## Owner Mobile UAT Blocking（2026-08-05）

### 已確認原因

- `demo/base.html`的desktop navigation含「幹部台」，但mobile breakpoint會隱藏整個desktop nav。
- Mobile bottom navigation只有首頁、賽程、活動與我的，沒有幹部台或活動管理入口。
- 因此officer demo session在手機上無法從可見UI到達`/demo/officer`及Event Builder；直接輸入URL不算可接受導覽。

### 必要補正

- 當`demo_member.demo_role == 'officer'`時，在mobile navigation提供清楚的「幹部」入口，至少可到達幹部工作台，再進入活動管理。
- 非officer demo member不得顯示幹部入口；Event Builder既有server-side officer guard仍須保留。
- 4／5欄mobile navigation需在約375px保持可讀、touch target合理且不造成橫向捲動。
- 新增response HTML與CSS contract tests，分別驗證officer可見、member不可見及mobile欄數／可達路徑。
- 重跑完整Web Portal tests、compile與diff checks；不得擴張至正式RBAC或production UI。

瀏覽器自動化工具本輪仍無法連線，但Owner的實機／手機版觀察已構成直接UAT證據，不需要等待工具才能判定此缺陷。

## Mobile UAT補正驗收

- Fix commit：`e9a0210`
- Report head：`e45c33d`
- Officer session的mobile bottom navigation現在為五欄並顯示「幹部」，可依可見連結到達`/demo/officer`及Event Builder。
- Non-officer session維持四欄，response不輸出mobile／desktop幹部入口；server-side builder guard仍回403。
- Mobile CSS採`repeat(5,minmax(0,1fr))`、54px touch target、可縮欄位及overflow限制，沒有固定min-width。
- Work重跑45項Web Portal tests全部通過，2項既有Windows platform skips；compileall與`git diff --check`通過。

Work結論恢復為`accepted`。Owner仍可就實際手機視覺提出非安全性調整；Python 3.10及自動化browser visual仍未驗證。

## PR與Python 3.10證據

- Owner後續授權push與建立PR，但未授權merge。
- Branch：`codex/prototype-web-portal-team-events`
- PR：#37 `feat(web-portal): prototype team operations and composite events`
- GitHub Actions run：`31021863646`
- Job：`92360319877`，`Python 3.10 unittest suite`成功。
- Hosted runner完成Web Portal tests及game broadcast、notify cron、deployment wrapper、update schedule與LINE webhook回歸。

因此Python 3.10限制已解除；browser automation視覺證據仍未補齊，Owner已完成至少一次mobile UAT並促成officer入口修正。
