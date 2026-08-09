# TASK-045 Work 驗收

- 日期：2026-08-06（Asia/Taipei）
- Branch：`codex/deploy-task044`
- 實作commit：`6000e2ee791b808a2cb1a27cd2b97ac9f7fa9137`
- 結論：`accepted`

## 實際查驗

- LINE attendance postback已移除`shared_module.web_cache` import與同步HTTP呼叫，未增加替代endpoint、retry或跨服務副作用。
- 全repository無其他程式caller後，`shared_lib/shared_module/web_cache.py`已刪除。
- 新測試以fail-on-network覆蓋新回覆、相同回覆、未完成初次互動、未配對、過期、取消、12小時內異動通知與首次提示。
- DB add、回覆訊息與既有late notification條件未被改寫。
- Web Portal `/attendance`無cache invalidation route，每次有效request重新取得Member、邀請中賽事與attendance analyzer結果。

## Work獨立驗證

```text
python -m unittest discover -s functions/line_webhook_handler/tests -v
Ran 18 tests - OK

python -m unittest discover -s apps/web_portal/tests -v
Ran 101 tests - OK (skipped=2)

python -m compileall -q functions/line_webhook_handler shared_lib/shared_module apps/web_portal
OK

git diff --check
OK
```

Work另重新執行`setup.py sdist`，產物成功建立且tar內容不含`shared_module/web_cache.py`；repository搜尋只剩測試對不存在route的否定斷言。

## 限制與後續

- 本機工作區缺完整`line-bot-sdk`；webhook tests使用repository內dependency stubs。Codex另完成shared sdist安裝驗證與61個檔案的Python 3.10 grammar check。
- PR需由hosted Python 3.10 CI安裝實際requirements後再驗證，不可只依賴本機shim。
- 本任務若後續部署，只需LINE webhook Cloud Functions Gen2及重建的shared artifact，不需部署Web Portal。
- 尚未push、PR、merge、部署、存取production或發送通知。
- 後續效能工作應先分段量測container cold start、DB connection與attendance query；在有證據前不重建跨服務cache。若瓶頸為冷啟動，評估Cloud Run minimum instances／startup CPU；若為DB則優先connection pooling與query/index，只有實際查詢壓力需要時才評估共享Redis短TTL。
