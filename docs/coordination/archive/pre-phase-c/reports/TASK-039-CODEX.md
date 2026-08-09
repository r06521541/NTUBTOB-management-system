# TASK-039 Codex 完工報告

更新時間：2026-08-06（Asia/Taipei）

## 任務狀態

- 狀態：`ready_for_review`
- Branch：`codex/task-038-closeout`
- Task base commit：`bd0ddd6`
- Implementation base commit：`1c32d0a`
- Implementation commit：`dbdd287`
- 未 push、未建立 PR、未 merge、未部署

## 實作結果

- `/redirect-to-login`不再以meta refresh或JavaScript自動跳轉，改為使用者明確選擇一般LINE登入或browser fallback。
- 兩個入口均使用`url_for`產生站內URL並保留同一個已驗證return path；每次點擊仍由既有`/line/login`建立fresh nonce與signed state。
- Browser fallback明確使用`mode=browser`及`disable_auto_login=true`；一般登入仍允許LINE支援的auto-login。
- 重複`next`在產生登入入口前回400；外部或不安全return path fail closed至首頁。
- 登入、invalid-state與等待核可頁共用mobile-first本機樣式、隊徽、清楚focus與至少52px操作目標。
- 等待核可頁移除外部Bootstrap；沒有User-Agent sniffing、custom scheme、外部圖片／字型／script或OAuth安全機制變更。

## 修改檔案

- `apps/web_portal/app.py`
- `apps/web_portal/static/auth.css`
- `apps/web_portal/templates/redirect_page.html`
- `apps/web_portal/templates/line_login_error.html`
- `apps/web_portal/templates/not_authenticated.html`
- `apps/web_portal/tests/test_admin_security.py`
- `apps/web_portal/README.md`

## 驗證

使用bundled CPython執行：

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 75 tests — OK (skipped=2)

python -m compileall -q apps/web_portal
OK

ast.parse(..., feature_version=(3, 10))
Python 3.10 grammar OK: 16 files

python tools/deploy_web_portal.py
Preflight passed for web-portal; no cloud or HTTP commands were run.

git diff --check
OK
```

兩項skip是既有Windows缺少Unix`make`／`sh`的deployment contract coverage，與本次變更無關。測試未呼叫真實LINE、HTTP或DB。

## 未驗證與限制

- 尚未以hosted Python 3.10 runner驗證；目前只有Python 3.10 grammar check。
- 尚未做375px實體瀏覽器視覺驗收或LINE in-app、iOS Safari、Android Chrome、desktop QR真實操作。
- 明確雙入口改善復原路徑，但無法保證iOS／Android會將一般登入handoff至LINE App。
- 未讀取Secret或`.env.yaml`，未存取production、DB、Cloud Run、IAM、schema或通知。
- Push、PR、merge及deployment未獲本輪授權。
