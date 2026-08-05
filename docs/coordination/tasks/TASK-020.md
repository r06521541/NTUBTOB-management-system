# TASK-020：強化 LINE Webhook 公開入口並建立離線安全測試

狀態：`planning`
優先級：P1
規劃者：Work
執行者：Codex（待 Owner 批准）
Base commit：`b053fce6b60c58b5dca597f4e4962f63d016a44a`

## 1. 任務目標

讓公開的 LINE webhook 在缺少或無效 `X-Line-Signature` 時明確 fail closed，且不因未受信任請求觸發資料庫、LINE、Discord 或其他外部副作用；同時以 Python 3.10 可執行的離線測試固定 Functions Framework production entry point 與 Flask local entry point 的一致行為。

此任務只修改 repository、執行離線測試與 PR CI；不得部署、呼叫 production webhook、讀取 production DB、發送真實通知或操作 Secret／IAM／Scheduler。

## 2. 已確認問題

- `functions/line_webhook_handler/main.py` 直接以 `request.headers['X-Line-Signature']` 取值；缺少 header 時會拋出 `KeyError`，形成 500。
- `main.py` 與 `app.py` 捕捉 `InvalidSignatureError` 後仍回傳 `OK`／HTTP 200，無效請求未被 HTTP 狀態明確拒絕。
- 兩個入口在無效簽章時呼叫 Discord alarm；公開端點可被任意請求觸發，形成外部副作用與告警放大風險。
- production entry point `main` 與 local Flask callback 有重複的 ingress 邏輯，未見相對應測試，行為容易漂移。
- LINE SDK 的 signature verification 已存在於 `webhook.handle_event()`／`WebhookHandler.handle()`；不得自行改寫或降低驗證演算法。

## 3. 使用者價值

- 無效 webhook 不會進入球隊資料、出席回覆或通知處理。
- 掃描、誤送與缺少 header 的請求不會製造 Discord 告警或其他外部成本。
- production 與 local endpoint 對相同輸入有一致、可回歸驗證的狀態碼。
- 後續修改 webhook 時，CI 能捕捉 signature boundary 退化。

## 4. 工作範圍

### 4.1 共用 ingress 邊界

- 建立一個小型、可注入 dispatch callable 的 ingress helper，供 `main.py` 與 `app.py` 共用。
- 先取得 raw request body與 `X-Line-Signature`，不得在驗證前解析或執行事件邏輯。
- 缺少或空白 signature：回傳 HTTP 400，不呼叫 dispatch。
- SDK 拋出 `InvalidSignatureError`：回傳 HTTP 400，不回傳例外內容、不呼叫 Discord／LINE／DB／cache。
- 合法 signature 且 dispatch 完成：維持現有 HTTP 200 與 `OK` response body。
- 非 signature 類型的程式錯誤不得偽裝成成功；保持平台可觀察的 5xx 語意，且不要把 secret、signature 或完整 request body寫入 log／response。

### 4.2 Production／local parity

- `functions/line_webhook_handler/main.py` 仍保留 `@functions_framework.http` 的 `main` entry point。
- `functions/line_webhook_handler/app.py` 仍保留 `POST /` local Flask route。
- 兩者必須委派相同 ingress helper，不維護兩份錯誤處理規則。
- 不修改 `webhook.py` 的業務事件分派、出席寫入、訊息模板或 LINE reply 行為，除非只為可測試 import 做最小必要調整且能證明相容。

### 4.3 離線測試與 CI

- 新增 `functions/line_webhook_handler/tests/`，至少涵蓋：
  - production entry point：缺少 header、空白 header、無效 signature、有效 request。
  - Flask route：相同四種情境與狀態碼／body parity。
  - 無效／缺少 signature 不呼叫 webhook dispatch、Discord、LINE、DB、cache或任何網路。
  - dispatch 發生非 signature 例外時不得回 200。
- 測試以 stub/mock 隔離 LINE SDK、shared library models、Discord與外部 HTTP；不得依賴 `.env.yaml`、secret、production DB或網路。
- 將新 suite加入現有 Python 3.10 GitHub Actions workflow，維持 `contents: read` 與現有 pinned actions。

### 4.4 文件

- 更新 `functions/line_webhook_handler/README.md`（目前不存在則建立精簡版本），說明公開端點仍依 LINE signature保護、400/200契約與離線測試命令。
- Codex完成後更新 report；Work驗收後更新 review、`PROJECT_STATE.md`與`HANDOFF.yaml`。

## 5. 非目標

- 不部署 Cloud Functions，不呼叫 production webhook或重送 LINE event。
- 不修改 LINE channel credentials、Secret Manager、IAM、公開 trigger或 Scheduler。
- 不修改 database schema、models、attendance規則或 cache endpoint。
- 不實作 webhook event idempotency、重試機制、速率限制或 WAF；這些可另立任務。
- 不全面重寫 `webhook.py`，不更換 LINE SDK或 Functions Framework。
- 不新增第三方 runtime dependency。

## 6. 設計決策

- HTTP 400用於「缺少或無效 signature」，避免回 200讓未受信任請求看似已接受。
- signature失敗不發 Discord alarm；端點是公開邊界，攻擊者不應能直接觸發正式通知。平台 request metrics/log仍可供後續觀察，但本任務不新增含 payload的logging。
- 共用 helper只處理 ingress contract，不承擔 LINE event domain logic，使變更維持小而可驗證。
- 測試直接證明 dispatch 是否被呼叫，而不是只比對 response文字。

## 7. 驗收條件

- 缺少、空白或無效 `X-Line-Signature` 均回 HTTP 400，沒有業務或外部副作用。
- 合法 request 只 dispatch一次並回 HTTP 200／`OK`。
- production與local入口的四種核心行為一致。
- unexpected dispatch failure不是HTTP 200，且輸出不含signature、secret或完整body。
- 現有 LINE SDK signature verification仍保留，既有 event handlers未被移除。
- 新舊測試可離線執行並通過，Python 3.10 CI通過。
- `git diff --check`與受影響模組compile/import check通過。

## 8. 驗證命令

```powershell
python -m unittest discover -s functions/line_webhook_handler/tests -v
python -m unittest discover -s apps/game_broadcast_service/tests -v
python -m unittest discover -s apps/notify_cronjob_service/tests -v
python -m unittest discover -s functions/update_game_schedule/tests -v
python -m unittest discover -s tools/tests -v
python -m compileall -q functions/line_webhook_handler
git diff --check
git status --short
```

若本機預設 Python 不是 3.10，可使用 repository 可用的 Python 做離線驗證，但必須由 GitHub-hosted Python 3.10 runner提供最終證據。

## 9. 預估影響範圍與依賴

- 預估檔案：`functions/line_webhook_handler/main.py`、`app.py`、新增 ingress helper、tests、README及CI workflow。
- 依賴：既有 `line-bot-sdk==3.11.0`、Functions Framework與Flask；不新增套件。
- 風險：LINE對非2xx可能重送事件；這是拒絕無效簽章的預期行為，合法事件仍維持200。測試不得使用真實簽章或token。

## 10. PR 工作包（待 Owner 批准）

若 Owner 接受此任務，建議同時批准 Codex：

- 建立 `codex/harden-line-webhook-ingress` branch。
- 建立描述性 local commits、push並建立 Draft PR。
- 執行離線測試與 GitHub Actions，於同一 PR更新 Codex report及交棒文件。

仍不包含 ready／merge、deployment、production request、正式通知、production DB、Secret／IAM／Scheduler或其他雲端操作；merge須由Owner在Work驗收後另行批准。
