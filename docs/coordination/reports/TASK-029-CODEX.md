# TASK-029 Codex 實作報告

更新時間：2026-08-06T03:55:00+08:00

## 任務狀態

- 狀態：`ready_for_review`（Owner 選擇的 original-browser 路線已完成 repository-only 修正）
- branch：`codex/fix-line-login-state-continuity`
- base commit：`196c2087a1bfdf816f16aafc267c7008aa376f41`
- implementation commit：`c771961d2f777f9153a41ecef131d3623024c5cf`
- Work review commit：`4511383d1b0e8639b5c3db04c786cfec0a747dd9`
- security correction commit：`6966f6ac3b92be61334a1fc5b4adda36bb7ef7b6`
- original-browser commit：`0a96355af0df073b77ad5d1432a392fd3833dc96`
- push／PR／CI：未授權，未執行

## 實際修改

- 將 OAuth state 改為使用 Flask `SECRET_KEY`、專用 salt 與 timestamp 的 self-contained signed state，不再依賴起始瀏覽器的 session cookie。
- state 僅保存隨機 nonce 與已驗證的站內 return path，TTL 為 600 秒；缺少、過期、竄改或格式錯誤皆在 LINE／DB 呼叫前回應 400。
- callback 可在不同 Flask test client（模擬 LINE App 與外部瀏覽器切換）完成登入，並保留安全的站內返回位置。
- 外部、scheme-relative 與非絕對 return target 全部降級至站內預設頁，避免 open redirect。
- LINE token／profile requests 加入 10 秒 timeout、HTTP status 與 JSON／必要欄位檢查；失敗時回應不含 token、Secret 或上游 payload 的 502。
- 保留既有 LINE callback URI、member lookup、session identity 與未核可頁面行為；未修改 schema 或正式設定。
- README 補充跨瀏覽器 callback、安全邊界與離線測試限制。

## 修改檔案

- `apps/web_portal/app.py`
- `apps/web_portal/line_login.py`
- `apps/web_portal/tests/test_admin_security.py`
- `apps/web_portal/tests/test_line_login.py`
- `apps/web_portal/README.md`
- `docs/coordination/reports/TASK-029-CODEX.md`
- `docs/coordination/PROJECT_STATE.md`
- `docs/coordination/HANDOFF.yaml`

## 驗證命令與結果

使用 bundled CPython 3.12：

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 52 tests — OK (skipped=2)

python -m compileall -q apps/web_portal
通過

git diff --check
通過
```

兩個 skips 是 Windows 缺少 Unix `make`／`sh` 的既有 deployment contract；TASK-029 新增測試沒有 skip。Black／isort 未執行，因 bundled runtime 未安裝兩項工具；未下載依賴或修改環境。

## 安全與未執行事項

- 未呼叫真實 LINE endpoints、production DB、Secret Manager 或 production logs；所有 HTTP 與 models 均為 mock。
- 未讀取 `envs/**/.env.yaml`、Secret payload 或真實管理者 ID。
- 未部署、push、建立 PR、merge，未修改 schema、IAM、Secret、Scheduler 或 production data。
- 離線測試不能證明 LINE Developers callback 設定、production Secret、跨 App/browser 真實切換或 Supabase lookup 正確；需合併與部署另案批准後人工驗證。

## Work review 後安全補正

- Work 正確指出原 self-contained signed state 是可轉交 bearer：簽章只能防竄改，不能證明 callback 屬於發起登入的 browser transaction。
- callback 現在同時要求 signed state nonce 與發起瀏覽器 session nonce 以 constant-time comparison 相符；跨 session callback 在 LINE／DB 前回 400，不會建立登入 session。
- return path 額外拒絕反斜線、ASCII control characters，以及 encoded slash、backslash、control、percent 等模糊 separator。
- `access_token`、`userId` 必須為非空字串，`displayName` 必須為字串；無效 shape 回 502，且不執行後續 HTTP／DB。
- original-browser 修正後 55 項 Web Portal tests 通過，2 項既有 Windows make/sh tests 跳過；compile、Python 3.10 grammar 與 diff check 通過。

## Blocking 與 Owner 可選方案

在 callback browser 不持有原 session cookie，且不新增共享一次性狀態或使用者確認步驟時，伺服器無法同時證明原始 browser transaction 並直接在另一瀏覽器建立登入 session。因此 TASK-029 的跨瀏覽器目標無法在目前範圍安全完成。

Owner 可另案選擇：

1. 優先盤點／調整 LINE Login 的 browser return 行為，使 callback 回到原本 external browser；維持現有 session-bound OAuth state，不新增儲存層。
2. 設計 two-phase login：callback 只把結果寫入 shared one-time transaction store，原始瀏覽器憑 session-bound secret claim 後才建立 session。需要選定具 TTL／atomic consume 的共享儲存、確認 UI、部署與 rollback 設計，但不一定需要修改正式 member schema。
3. 維持目前安全 fail-closed 行為，接受需要在 LINE 內建瀏覽器登入；不接受以 transferable signed bearer state 直接建立 session。

不建議接受 login-CSRF/session swapping 風險，也不建議把 PKCE verifier 放進可轉交 state；兩者都不能解決原始 browser transaction binding。

## Original-browser 官方文件診斷

Owner 選擇優先讓 callback 回到原 external browser。LINE 官方說明 mobile external browser 的 auto-login 會透過 iOS Universal Links／Android App Links 啟動 LINE App；auto-login 失敗與 CSRF 都可能表現為 state mismatch，無法只靠 mismatch 區分。官方建議失敗後使用 `disable_auto_login=true` 重新進入 authorization URL，使登入畫面留在 browser flow：

- [Integrating LINE Login with your web app](https://developers.line.biz/en/docs/line-login/integrate-line-login/)
- [How to handle auto login failure](https://developers.line.biz/en/docs/line-login/how-to-handle-auto-login-failure/)
- [LINE Login FAQ: auto login environments](https://developers.line.biz/en/faq/tags/line-login/)

### Flow matrix

| 起點 | LINE 官方已確認行為 | 本次策略 | 尚待真實驗證 |
| --- | --- | --- | --- |
| Desktop browser | LINE PC 不支援 auto-login；可使用 browser email／QR／SSO | `disable_auto_login=true`，維持同一 browser callback 與 session nonce | Desktop callback 與既有會員頁 |
| iOS Safari | 支援 auto-login，透過 Universal Links 啟動 LINE App；private browsing／OS 條件可能失敗 | 停用 auto-login，改走 Safari browser login | Safari 正常／private mode UX |
| Android Chrome | 支援 auto-login，透過 App Links 啟動 LINE App | 停用 auto-login，改走 Chrome browser login | Chrome 與 Custom Tab 差異 |
| LINE in-app browser | 支援 auto-login；Owner 已確認舊流程可用 | 停用 auto-login但保留同一 in-app cookie transaction | 是否多出 email／確認畫面 |
| 其他 iOS browser／無 LINE App | 官方不保證 auto-login | browser login，不依賴 app handoff | 個別 browser 支援度 |

### Repository cookie／callback 查驗

- `LINE_REDIRECT_URI` 固定為 production Cloud Run host 的 `/line/callback`，與 repository 既有 production inventory URL 相同；LINE Console 必須登記完全相符的 callback URL，但本輪未查 Console。
- Repository 未設定 `SESSION_COOKIE_DOMAIN`，所以 session cookie 是 host-only；未設定獨立 path，Flask application root 為 `/`，可涵蓋 `/line/login` 與 `/line/callback`。
- Repository 未明設 `SameSite`／`Secure`。callback 是 LINE 導回的 top-level GET；是否有 browser policy、proxy 或未記錄 custom domain 造成 cookie scope 差異，仍需真實瀏覽器與 response cookie attributes 驗證。
- 若使用者從 custom domain 或其他 hostname 發起登入，但 callback 固定回 Cloud Run hostname，host-only session 必定不連續。Repository 沒有 custom domain 證據，不能憑空判定 production 是否存在此入口。

### Repository-only 修正

- authorization URL 新增 `disable_auto_login=true`，保留 signed state 與 session nonce binding。
- 先加入 authorization query contract test並確認缺少參數時失敗，再做單一參數修正。
- 這是官方建議的 browser login fallback，但離線測試不能證明 iOS／Android 最終 user-agent；合併與部署後仍需 Owner 以 Safari／Chrome／LINE in-app browser 做受控人工驗證。
