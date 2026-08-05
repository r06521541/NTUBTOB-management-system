# TASK-032 Codex 完工報告

更新時間：2026-08-06（Asia/Taipei）

## 任務狀態

- 狀態：`ready_for_review`
- Branch：`codex/version-web-session-cookie`
- Base commit：`15881c5b886fc87e92cf0e6aeb5b4dca9d1df9c4`
- Implementation commit：`08ccd88d5aa2caa325d65c14be3bea7903224b84`
- Security correction commit：`e2b769a`
- 未 push、未建立 PR、未 merge、未部署

## 實作結果

- 將 Flask session cookie 版本化為 `ntubtob_web_session_v2`。
- 明確設定 host-only、`Path=/`、`HttpOnly`、`SameSite=Lax`；production 與所有未明確開啟的環境均強制 `Secure`。
- 只有 `WEB_PORTAL_ENV=development` 且 `WEB_PORTAL_DEMO_MODE=true` 的雙重 gate demo 允許 HTTP cookie。
- 瀏覽器送出舊 Flask `session` cookie 時，只送出該 host、root-path cookie 的到期指令；不讀取、記錄或複製 cookie value。
- 無效、過期或跨 session OAuth state 仍在 LINE token/profile、資料庫及通知之前回覆 400。
- 無效 state 只會清除 `oauth_state_nonce`、`next_url` 等登入交易暫存，保留既有 `user_id`、`member_id`、`member`、`display_name`；因此任意 callback GET 不能登出已認證使用者。
- 安全重試頁只會進入 `/line/login` 建立全新 nonce/state，不會重用舊 code/state。
- 保留既有 LINE Login、return path、Member 查詢與 demo 行為。

## 變更檔案

- `apps/web_portal/app.py`
- `apps/web_portal/templates/line_login_error.html`
- `apps/web_portal/tests/test_admin_security.py`
- `apps/web_portal/tests/test_demo_portal.py`
- `apps/web_portal/README.md`
- `docs/coordination/reports/TASK-032-CODEX.md`
- `docs/coordination/PROJECT_STATE.md`
- `docs/coordination/HANDOFF.yaml`

## 驗證

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 58 tests in 0.809s
OK (skipped=2)

python -m compileall -q apps/web_portal
OK

ast.parse(..., feature_version=(3, 10))
Python 3.10 grammar OK

python tools/deploy_web_portal.py
Preflight passed for web-portal; no cloud or HTTP commands were run.

git diff --check
OK
```

兩項 skip 是既有 Windows 環境缺少 Unix `make`／`sh` 的 deployment contract coverage，與本次變更無關。第一次在未 commit 的 dirty worktree 執行 deployment preflight 時依設計 fail closed；建立實作 commit、工作目錄乾淨後重跑通過。

## 未驗證與風險

- 沒有真實瀏覽器、LINE Developers、production runtime 或 Cloud Run 驗證；offline tests 不等於線上 cookie migration 已成功。
- 版本化 cookie 會讓所有使用者重新登入，這是刻意的 migration 行為。
- 只能精確淘汰目前 host、`Path=/` 的舊 Flask cookie；repository 沒有證據顯示過去曾設定其他 Domain 或 Path。即使存在其他 scope，新 cookie 名稱也不會讀取它。
- 沒有讀取 secret、`envs/**/.env.yaml`、production DB，也沒有呼叫 LINE、HTTP、gcloud 或通知。
- 沒有 schema、migration、Secret、IAM、Scheduler 或 deployment config 變更。

## Work 驗收重點

- 確認 `Secure=False` 僅能由雙重 gate demo 觸發。
- 確認 legacy deletion 不建立寬化 Domain，也不回顯 cookie value。
- 確認 invalid-state 兩條路徑都清除 OAuth 暫存、在任何外部或 DB 呼叫前停止，且重試產生 fresh transaction。
- 確認 invalid-state 與 cross-client callback 僅清除 OAuth 暫存、保留 authenticated identity，避免 logout-CSRF／DoS。
- 若接受，Owner 尚須另行批准 TASK-032 PR 工作包與後續 production rollout。
