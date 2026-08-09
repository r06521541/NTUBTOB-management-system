# TASK-020 Work Review

日期：2026-08-05
結論：`accepted`
Branch：`codex/harden-line-webhook-ingress`
Codex驗收HEAD：`e256af2debcdc9c70b48656e52c48c39bb239a57`
Draft PR：[#34](https://github.com/r06521541/NTUBTOB-management-system/pull/34)

## 實際查驗

- Working tree在Work修正Codex report的兩行Markdown尾端空白前為乾淨；該修正會併入本次Work驗收commit。
- PR #34為open／draft／mergeable，head與本機Codex HEAD一致。
- 實作diff限定於LINE webhook ingress、離線測試、CI step、README及協作文件；未修改`webhook.py`業務事件、shared library、schema或deployment設定。
- `main.py` Functions Framework entry point與`app.py` Flask route共同委派`ingress.py`，沒有維護兩份signature錯誤規則。
- 現有LINE SDK `WebhookHandler.handle()`仍負責signature驗證，沒有自行改寫或降低驗證。

## 驗收條件

- 缺少或空白`X-Line-Signature`：HTTP 400，且在讀取body／dispatch前停止。
- SDK回報無效signature：HTTP 400，不觸發原有Discord alarm；fake dispatcher證明不進入後續event處理。
- 合法request：恰好dispatch一次並維持HTTP 200／`OK`。
- Unexpected dispatch exception：不回200，外部response／重新拋出的例外只含泛化訊息，不含底層敏感文字、signature或body。
- Production與local入口的成功、拒絕及5xx語意一致。
- CI維持`contents: read`與pinned actions，只新增既有依賴安裝及webhook suite。

## Work重跑證據

使用Codex workspace bundled CPython 3.12.13離線執行：

- LINE webhook ingress：10/10通過。
- Game broadcast：28/28通過。
- Notify cronjob：9/9通過。
- Update schedule：5/5通過。
- Scheduled deployment wrapper：11/11通過。
- `python -m compileall -q functions/line_webhook_handler`：通過。
- `git diff --check b053fce`：修正Codex report兩行尾端空白後通過。

GitHub-hosted Python 3.10 final Codex-head run `30984636639`／job `92236491079`：`SUCCESS`。Work驗收commit push後仍須等待其最終CI成功，才可交Owner決定merge。

## Blocking問題

無。

## 殘餘風險與未驗證

- 沒有對LINE或production endpoint送出request；線上Functions runtime與LINE實際重送行為尚未驗證。
- 合法event的domain handlers不是本任務新增整合測試範圍；本次只固定公開ingress contract。
- 無效signature回400可能使發送端重試，屬明確拒絕未受信任請求的預期取捨。
- Unexpected exception以泛化`WebhookDispatchError`呈現；可觀察到5xx與安全錯誤類型，但不保留底層例外文字，避免payload或credential外洩。

## 安全邊界

未部署、未呼叫production webhook、未連production DB、未發送LINE／Discord、未讀取Secret，亦未操作IAM、Scheduler、schema、ready或merge。

## 結論與下一步

`accepted`。等待Work驗收commit的Python 3.10 CI成功後，交由Owner決定是否將PR #34標記ready並merge。Merge不代表Cloud Functions deployment授權。
