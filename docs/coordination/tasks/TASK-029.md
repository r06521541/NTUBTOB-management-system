# TASK-029：修正跨瀏覽器 LINE Login OAuth State Continuity

狀態：`ready_for_codex`
優先級：P1 authentication reliability
規劃者：Work
預定執行者：Codex
Base commit：`196c2087a1bfdf816f16aafc267c7008aa376f41`

## 1. 問題與使用者影響

Owner 已在 production 重現：需要登入的 Web Portal 頁面於 LINE 內建瀏覽器可用，但從一般網頁瀏覽器進行 LINE Login 時，callback 顯示 `Invalid state parameter`。

目前 `/line/login` 把隨機 OAuth state 存在 Flask browser session；`/line/callback` 只接受同一 session cookie 中的 state。手機 LINE Login 若由外部瀏覽器切換至 LINE App／LINE 內建瀏覽器再回 callback，兩個 user agent 不共享 cookie，因此合法登入也會被拒絕。

使用者影響：一般 Chrome、Safari 或桌面瀏覽器可能無法登入受保護頁面，管理者 allowlist 即使設定正確也無法使用。

## 2. 任務目標

在不降低 OAuth CSRF／state 防竄改邊界的前提下，使 LINE Login callback 不依賴登入起始瀏覽器的 Flask session cookie，讓 LINE App／內建瀏覽器切換後仍能安全完成登入。

## 3. 已確認事實、推論與待確認事項

### 已確認事實

- `/line/login` 目前產生隨機字串並寫入 `session['oauth_state']`。
- `/line/callback` 以 `session.pop('oauth_state', None)` 比對 request state；cookie 不連續時必定回傳 400。
- LINE redirect URI 目前固定為 production Cloud Run callback URL。
- Owner 已看到精確錯誤 `Invalid state parameter`。
- Flask session 由 runtime `SECRET_KEY` 簽章；目前 production 已使用 Secret Manager runtime binding。

### 合理推論

- 最可能原因是 LINE App／外部瀏覽器切換造成 session cookie 不連續，而不是 Member allowlist 或資料庫查詢；錯誤發生在 token exchange 與 DB lookup 之前。

### 待確認

- 問題是否只發生於特定 mobile browser／OS。
- LINE Developers Console 登記的 callback URL 是否只有目前 Cloud Run URL。
- production callback log 是否存在其他 state failures；本任務不得自行查 production logs，除非 Owner 另行批准唯讀診斷。

## 4. 設計決策

- 優先使用 Flask 既有相依鏈中的 `itsdangerous` 建立具專用 salt、timestamp 與 server-side signature 的 self-contained OAuth state。
- callback 驗證 state 的簽章與短期限，不再要求原瀏覽器帶回 Flask session cookie。
- state 只能承載最小必要資料，例如安全的站內 return path 與 nonce；不得包含 Secret、LINE user ID、Member ID 或個資。
- return target 只允許站內相對路徑；拒絕 absolute URL、scheme-relative URL、非本站 host、控制字元與其他 open-redirect 形式。
- state 必須具短期 expiration（建議 5–10 分鐘），過期、缺少、竄改、格式錯誤或用途 salt 不符時一律回傳安全的 400，不進行 token exchange、DB query 或通知。
- LINE token/profile request 必須保留既有產品流程，但新增明確 timeout、安全化錯誤處理與 response status/payload shape 驗證；錯誤不得輸出 access token、Channel Secret 或完整外部 response body。
- 不使用 process-local cache 作為唯一 state store，避免 Cloud Run multi-instance callback 落到不同 instance 時失敗。

## 5. 實作範圍

- 重構 `/line/login` 與 `/line/callback` 的 state 建立／驗證為可單元測試的 helpers。
- 將 authorization URL 透過安全的 URL encoding 建立，不手動串接未編碼 query values。
- 正規化並限制 `next`／return target；登入成功後只能 redirect 到站內 route。
- 對 LINE token 與 profile HTTP calls 設定 timeout，處理 transport error、非 2xx、invalid JSON、missing access token/user profile fields。
- 建立離線 route/helper tests，mock 所有 LINE HTTP 與資料庫 model calls。
- 保留現有 LINE Login channel、callback path、會員查詢、管理者 allowlist 與既有頁面行為。
- 更新 Web Portal README，說明跨瀏覽器 state、安全期限與 callback URL 前置條件。

## 6. 明確非目標

- 不修改 LINE Developers Console、callback URL、Channel Secret 或 Secret Manager。
- 不部署、不登入 production、不讀 production logs、不呼叫真實 LINE endpoints。
- 不連 production Supabase、不修改 schema、models 或 Member／LineUser 資料。
- 不實作 Google／Apple OAuth、LIFF、角色分級或新的登入供應商。
- 不修改管理者 allowlist 規則。
- 不以停用 state 驗證、接受任意 callback、固定 state、延長為無期限或降低 cookie/security 設定來解決問題。
- 暫不處理 session 中保存完整 `Member` object 的相鄰風險；另案評估，避免擴張本次登入 state 修正。
- 未取得 Owner PR 工作包前，不 push、不建立 PR；任何 merge 或 production 驗證均須另行批准。

## 7. 必要測試

至少涵蓋：

- 登入起始 client 與 callback client 不共享 session cookie，合法 signed state 仍可完成 callback。
- 正常同瀏覽器流程維持相容。
- state 缺少、竄改、過期、錯誤 salt、非法格式均 400，且沒有 LINE HTTP／DB／notification side effects。
- `next` 缺少時使用既有安全預設頁；合法站內 path 可保留。
- absolute、scheme-relative、不同 host、反斜線／控制字元等 return target 被拒絕或替換成安全預設。
- authorization URL 的 redirect URI、client ID、scope 與 state 正確 URL encoded。
- token/profile timeout、非 2xx、invalid JSON、缺欄位均產生不含敏感資訊的安全錯誤，且不建立登入 session。
- 已配對 Member 的成功流程仍寫入必要 session identity；未配對或找不到 Member 仍顯示等待核可頁。
- 管理者 route tests、demo tests 與 deployment contract tests 保持通過。

## 8. 驗收條件

- 可離線測試證明 callback 不再依賴起始 browser session cookie。
- 所有 invalid state 路徑 fail closed，token exchange 與 DB lookup 都不會執行。
- 不形成 open redirect、token/Secret disclosure 或無期限 replay window。
- 不新增資料庫 schema、Secret、environment variable 或第三方 dependency。
- Python 3.10 相容；受影響 tests、compile/import 與 `git diff --check` 通過。
- Codex report 明確說明實際 state format、TTL、return-path validation、HTTP timeout、未驗證 production 風險及所有變更檔案。

## 9. 建議驗證命令

```powershell
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q apps/web_portal
git diff --check
git status --short
```

測試不得發出外部 HTTP、不得讀取 `envs/**/.env.yaml`。

## 10. 啟動條件與後續 production 驗證

- PR #38／TASK-028 應先完成 Owner merge 決策，Work 再以 merge 後 `main` commit 填入本任務 base commit 並更新 `HANDOFF.yaml` 為 `ready_for_codex / codex`。
- 實作驗收與 CI 通過不代表 production 已修正。
- 後續若要部署與由 Owner 在一般瀏覽器重試 LINE Login，必須另立 exact production deployment／smoke-test 工作包；失敗時只讀診斷，不自行修改 LINE Console、Secret、IAM 或資料。

Owner 已批准 TASK-029 的本機實作與描述性 commit。未批准 push、PR、merge、production logs、LINE API、Secret／LINE Console 修改、部署或 production data 操作。
