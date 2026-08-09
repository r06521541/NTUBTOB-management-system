# TASK-038 Codex 完工報告

更新時間：2026-08-06（Asia/Taipei）

## 任務狀態

- 狀態：`ready_for_review`
- Branch：`codex/task-038-line-auto-login`
- Task base commit：`4b9ddd483a197d00a41403858efd36ff964e6e10`
- Implementation base commit：`b23bbecefd1cafe0e2a20f3de49a61b592a348fa`
- Implementation commit：`0e7be34`
- 未 push、未建立 PR、未 merge、未部署

## 實作結果

- 一般 `/line/login` authorization request 不再附加 `disable_auto_login`，恢復 LINE auto-login eligibility。
- 只有明確 allowlist 的 `mode=browser` 會加入 `disable_auto_login=true`；未知、重複或互相衝突的 mode，以及重複 `next` 參數，都在 LINE redirect 前回 400。
- normal 與 browser fallback 每次都建立新的隨機 nonce 與 server-signed state，並維持 callback 對 browser session nonce 的 constant-time comparison。
- signed-valid 但 session nonce 不符時，只把已驗證的安全站內 return path帶到錯誤頁的 fallback URL；缺少、竄改、過期或格式錯誤 state 一律使用固定 `/attendance`。
- 錯誤頁的「改用瀏覽器登入」會啟動全新 transaction，不重用失敗的 authorization code、state 或 nonce。
- 外部、模糊或 ambiguous return target 維持 fail closed；沒有 User-Agent sniffing、跨 browser bearer state或安全邊界降級。
- 既有 minimal identity session、cookie policy、CSRF、admin、roster 與 demo 行為保持不變。

## 修改檔案

- `apps/web_portal/app.py`
- `apps/web_portal/templates/line_login_error.html`
- `apps/web_portal/tests/test_admin_security.py`
- `apps/web_portal/README.md`
- `docs/coordination/reports/TASK-038-CODEX.md`
- `docs/coordination/PROJECT_STATE.md`
- `docs/coordination/HANDOFF.yaml`

## 驗證

使用 bundled CPython 3.12 執行：

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 71 tests — OK (skipped=2)

python -m compileall -q apps/web_portal
OK

ast.parse(..., feature_version=(3, 10))
Python 3.10 grammar OK: 16 files

python tools/deploy_web_portal.py
Preflight passed for web-portal; no cloud or HTTP commands were run.

git diff --check
OK
```

兩項 skip 是既有 Windows 缺少 Unix `make`／`sh` 的 deployment contract coverage，與本次變更無關。所有 LINE HTTP 與資料庫存取在測試中均使用 mock；未發出外部請求。

## 未驗證與限制

- 尚未使用 hosted Python 3.10 runner；目前只有 Python 3.10 grammar check，PR CI 需另行授權。
- 尚未在 LINE in-app browser、iOS Safari、Android Chrome 或 desktop browser 做真實登入；離線 URL contract不能證明 LINE 平台實際 auto-login／fallback UX。
- 未讀取 Secret、`envs/**/.env.yaml` 或 production DB；未呼叫 LINE、gcloud、Cloud Run、通知或其他外部服務。
- 未修改 schema、Secret、IAM、LINE Console、cookie policy、shared library或其他服務。
- Push、PR、merge 與 production deployment均未獲本輪授權。
