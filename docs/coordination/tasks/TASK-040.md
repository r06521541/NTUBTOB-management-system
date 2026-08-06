# TASK-040：修正手機 LINE 登入引導與失敗復原 UX

## 背景

Owner 已在 iOS Safari 實測確認：一般 LINE 登入可能開啟 LINE App，但 callback 會落在不同的瀏覽器／cookie context，因此既有 session nonce 無法延續，系統會正確拒絕並顯示「登入狀態已過期」。此時若在同一支手機選擇 `disable_auto_login=true` 的瀏覽器登入，LINE 可能只提供 QR Code；同機掃描無法形成可用的復原流程。

產品策略已確認：

- 手機 LINE 使用者以 LINE 內建瀏覽器開啟 Portal 為主要支援路徑。
- 電腦瀏覽器維持現有 LINE 帳號／QR Code 登入方式。
- 手機外部瀏覽器的 LINE App auto-login 僅視為 best-effort，不承諾能跨瀏覽器 context 返回。
- 未來若需要穩定支援手機外部瀏覽器，另行評估 Google／Apple 等登入方式；本任務不實作。

## 使用者價值

- 避免 iPhone／Android 使用者被引導至無法在同一支手機完成的 QR Code 死路。
- 登入失敗時提供符合實際支援能力的下一步，而不是反覆重試相同流程。
- 保留目前已可用的 LINE 內建瀏覽器與電腦登入。

## 範圍

1. 修正登入選擇頁文案與動作標示：
   - 手機使用者清楚知道應回到 LINE 內開啟 Portal。
   - 電腦使用者清楚知道瀏覽器登入可能使用 LINE 帳號或 QR Code。
   - 不再把「改用瀏覽器登入」描述為手機外部瀏覽器的可靠備援。
2. 修正 signed-valid nonce mismatch／登入狀態過期頁：
   - 不再直接推薦手機走同機 QR Code 備援。
   - 提供回到登入說明頁或重新選擇方式的安全 same-site 入口。
   - 保留已驗證的 safe internal return path。
3. 更新 Web Portal README，記錄目前支援矩陣與限制。
4. 更新或新增離線測試，驗證重要文案、連結與既有安全行為。

## 非目標

- 不修改 OAuth `state`、nonce、session cookie 或 CSRF 驗證。
- 不建立可跨瀏覽器轉移的 bearer state，不降低 fail-closed 行為。
- 不加入 user-agent sniffing、自動跳轉、`line://` custom scheme 或 LIFF。
- 不實作 Google／Apple OAuth、帳號綁定或新 authentication provider。
- 不修改 LINE Developers Console、Secret、IAM、資料庫、schema 或 production 設定。
- 不部署、不發送 LINE 訊息、不連線 production DB。

## 設計要求

- 保持正常 `/line/login` 與 `mode=browser` route 的既有安全語意；本任務主要是呈現與復原導引。
- 登入狀態過期頁的下一步必須使用 server 產生的 same-site URL，並維持 return target 驗證。
- 不根據裝置猜測或隱藏功能；以中性、準確的支援說明呈現。
- 手機畫面約 375px 不得產生水平捲動。
- 延續現有 Flask/Jinja 與 auth CSS，不引入新 framework 或 dependency。

## 驗收條件

1. 登入選擇頁明確說明：手機建議在 LINE 內開啟；電腦可使用瀏覽器／QR Code。
2. 頁面不再宣稱 iPhone Safari／Android 外部瀏覽器可用「改用瀏覽器登入」可靠復原。
3. 登入狀態過期頁不再直接將使用者導入同機 QR Code 死路，且可安全返回登入說明頁。
4. 正常 LINE Login、browser-mode authorization URL、state/nonce 驗證均未被放寬或移除。
5. 沒有 meta refresh、JavaScript 自動登入、UA sniffing 或外部 custom scheme。
6. 受影響測試離線通過，沒有外部 HTTP、DB 或通知副作用。

## 驗證命令

```text
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall apps/web_portal
git diff --check
git status --short
```

Windows 若沒有全域 `python`，使用 repository 工作環境提供的 Python executable。Hosted Python 3.10 驗證留待後續 PR 工作包，並非本機完成條件。

## 交付要求

- 實作與測試採一個描述性 commit，例如：
  `fix(web-portal): guide mobile users back to LINE for login`
- Codex 完成後更新 `docs/coordination/reports/TASK-040-CODEX.md` 與 `HANDOFF.yaml`，交回 Work 驗收。
- 本工作包不包含 push、PR、merge 或 deployment。

## Base commit

`7082afd4a1d9fe579f02956c77ecbc85b58fd7b7`
