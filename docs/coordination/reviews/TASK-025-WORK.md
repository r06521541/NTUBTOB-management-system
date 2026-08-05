# TASK-025 Work Review

驗收日期：2026-08-05
驗收者：Work
結論：`accepted`

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

TASK-025在批准的local prototype範圍內完成，沒有blocking問題。建議Owner先接受並實際瀏覽操作；後續產品調整繼續留在demo，正式schema另立discovery／migration任務。

