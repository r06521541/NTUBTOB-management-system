# TASK-040 Codex 完工報告

更新時間：2026-08-06（Asia/Taipei）

## 任務狀態

- 狀態：`ready_for_review`
- Branch：`codex/task-039-closeout`
- Task base commit：`7082afd4a1d9fe579f02956c77ecbc85b58fd7b7`
- Implementation base commit：`d84d63771e8bfa9d9f2446c84b8d8c09faed3e32`
- Implementation commit：`a369123`
- 未 push、未建立 PR、未 merge、未部署

## 實作結果

- 登入選擇頁改為明確區分手機與電腦：手機使用者回到 LINE 內開啟 Portal；電腦使用者才選擇瀏覽器登入並依 LINE 畫面使用帳號或 QR Code。
- 頁面明確說明外部手機瀏覽器的 LINE App handoff 可能遺失 cookie context，同一支手機也不適合使用 QR Code。
- 登入狀態過期頁不再直接啟動 `mode=browser`，而是透過 server 產生的 same-site URL 返回登入說明頁，並保留已驗證的 safe internal return path。
- 一般 `/line/login`、`mode=browser`、`disable_auto_login=true`、OAuth state 簽章、session nonce binding 與 fail-closed return-path 驗證均未放寬。
- 未加入 User-Agent sniffing、自動跳轉、custom scheme、外部 script 或新 dependency。

## 修改檔案

- `apps/web_portal/app.py`
- `apps/web_portal/templates/redirect_page.html`
- `apps/web_portal/templates/line_login_error.html`
- `apps/web_portal/tests/test_admin_security.py`
- `apps/web_portal/README.md`

## 驗證

使用 bundled CPython 3.12.13 執行：

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 75 tests — OK (skipped=2)

python -m compileall -q apps/web_portal
OK

git diff --check
OK
```

兩項 skip 是既有 Windows 環境缺少 Unix `make`／`sh` 的 deployment contract coverage，與本次變更無關。測試 mock LINE HTTP、資料庫與通知，不含 production 副作用。

第一輪因 bundled Python 尚未安裝 Web Portal 依賴而在 test discovery 失敗；之後從 `apps/web_portal/requirements.txt` 安裝 repository 鎖定依賴與本地 `dist/shared_lib-0.0.1.tar.gz`，完整重跑後通過。未修改 dependency manifest。

## 未驗證與限制

- 尚未由 hosted Python 3.10 runner 驗證；留待後續 PR 工作包。
- 尚未部署，因此新文案與 375px 實機畫面仍待 Work／Owner 驗收。
- Android 外部瀏覽器行為仍未知；本任務只將其標示為非保證路徑。
- 未讀取 Secret 或 `.env.yaml`，未存取 production、LINE Console、DB、Cloud Run、IAM、schema 或通知。
