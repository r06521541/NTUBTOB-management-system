# TASK-020 Codex Implementation Report

日期：2026-08-05  
狀態：`ready_for_review`  
PR：[Draft PR #34](https://github.com/r06521541/NTUBTOB-management-system/pull/34)

## Git 範圍

- Task base：`b053fce6b60c58b5dca597f4e4962f63d016a44a`
- Branch 起點包含 Owner 已批准的 TASK-020 規劃與授權 commits：`0c29220`、`7da93dd`
- Implementation commit：`a84ef6430d49aa6911bd79ed22828b0b5f14fac8`
- Branch：`codex/harden-line-webhook-ingress`

## 完成內容

- 新增共用 ingress helper，供 Functions Framework `main` 與 local Flask route 使用。
- 缺少或空白 `X-Line-Signature` 時，在讀取 body 或 dispatch 前回 HTTP 400。
- LINE SDK 拋出 `InvalidSignatureError` 時回 HTTP 400，不發 Discord alarm。
- 有效請求維持一次 dispatch 與 HTTP 200／`OK`。
- 非簽章例外維持 5xx，並轉成不含底層例外、signature 或 request body 的泛化錯誤。
- 未修改 `webhook.py` 的 SDK 驗證、事件 handlers、資料庫或通知業務行為。
- 新增 production／local parity 離線測試、README 與 Python 3.10 CI step。

## 驗證結果

本機 bundled CPython 3.12.13：

- LINE webhook ingress：10/10 通過。
- Game broadcast：28/28 通過。
- Notify cronjob：9/9 通過。
- Update schedule：5/5 通過。
- Scheduled deployment wrapper：11/11 通過。
- `compileall`：通過。
- `git diff --check`：通過。

GitHub Actions run `30984523040`／job `92236135835`：

- Python 3.10 unittest suite：`SUCCESS`（17 秒）。
- Workflow parser、Python 3.10 runtime 與新增 webhook suite 均已實跑。

## 安全邊界

- 測試在匯入 entry points 前以 fake webhook dispatcher 隔離業務模組；沒有 DB、LINE、Discord、cache 或網路呼叫。
- 未讀取 `.env.yaml` 或 Secret，測試只使用虛構 body／signature。
- 未部署、呼叫 production webhook、通知、操作 production DB、Secret、IAM、Scheduler 或 schema。
- PR 保持 Draft，未 ready 或 merge。

## 未驗證與殘餘風險

- 未向 LINE 或 production endpoint 發送 request；線上 Functions runtime 行為仍待未來精確部署授權後驗證。
- 合法 LINE event 的 domain handlers 未在本任務新增整合測試；本任務只固定 ingress contract，並保留原有 handler 程式碼。
- 對無效簽章回 400 可能使發送端重試，屬明確拒絕未受信任請求的預期行為。

## 變更檔案

- `.github/workflows/python-tests.yml`
- `functions/line_webhook_handler/README.md`
- `functions/line_webhook_handler/app.py`
- `functions/line_webhook_handler/ingress.py`
- `functions/line_webhook_handler/main.py`
- `functions/line_webhook_handler/tests/test_ingress.py`
- `docs/coordination/reports/TASK-020-CODEX.md`
- `docs/coordination/HANDOFF.yaml`
