# TASK-012 Codex Report

狀態：`ready_for_review`
執行者：Codex
base commit：`b25b3ad6ca3ba355756cc938259d11b7be163398`
head commit：`b25b3ad6ca3ba355756cc938259d11b7be163398`（本任務未 commit）

## 完成內容

- 新增 `/demo` 下的 mobile-first Web Portal MVP：登入原型、Dashboard、賽程列表、賽事詳情、個人頁與等待核可頁。
- 出席／不出席／待確認採 allowlist 驗證及 POST/redirect/GET，只寫 Flask session；重新登入或登出即清除。
- Demo 只在 `WEB_PORTAL_ENV=development` 及 `WEB_PORTAL_DEMO_MODE=true` 同時成立時啟用。缺任一 gate、大小寫錯誤或 production 值均回傳 404。
- Demo mode 不載入 production ORM、資料庫 engine、attendance helper 或 Discord notifier，並封鎖既有資料型 routes；乾淨 shell 不需 DSN、Secret 或外部 API 即可啟動。
- 建立本地 CSS、共用 Jinja layout/macros、desktop header、mobile bottom navigation、cards、buttons 與 status badges；引用 Owner 既有未追蹤 Logo，未修改原圖。
- 保留 `/line/login` 與 `/line/callback`；Google/Apple 與通知偏好明確標示為 prototype，不發 OAuth 或通知請求。
- 新增 Web Portal README 與完整離線 unittest。

## 驗證結果

測試 runtime 為 Python 3.12.13，不是 Python 3.10；Python 3.10 尚待 CI 或可用本機 runtime 驗證。

```text
C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s apps/web_portal/tests -v
10 tests passed

C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m compileall -q apps/web_portal
passed

git diff --check
passed
```

另以完全移除 `DSN_*`、`SECRET_KEY` 的 shell import `app`，確認 demo routes 與既有 LINE routes可註冊。測試將 ORM替身及 `requests.get/post` 設為不可呼叫後，主要 demo navigation仍全數回傳 200。

另以本機瀏覽器 375×812 viewport實際操作登入、Dashboard及賽事詳情；三頁的 `scrollWidth` 均等於 `clientWidth`（實際內容寬360px），沒有頁面級橫向捲動。Dashboard bottom navigation存在且 main content保留108px底部空間，賽事詳情三個回覆按鈕均可見。

## Prototype 與未驗證事項

- Google/Apple OAuth、通知偏好 persistence、正式出席寫入、管理員核可與跨裝置狀態皆未實作。
- 既有 production DB routes、LINE callback 與正式授權行為未在本任務驗證；demo mode會隔離這些資料型 routes。
- 375px本機瀏覽器的結構與溢位檢查已通過；視覺風格仍待 Owner以自己的手機／瀏覽器做主觀驗收。
- 未修改 schema、shared library、deployment、Secret、其他服務或 production資料；未部署、commit、push或建立PR。

## 變更檔案

- `apps/web_portal/app.py`
- `apps/web_portal/demo_data.py`
- `apps/web_portal/demo_portal.py`
- `apps/web_portal/README.md`
- `apps/web_portal/static/portal.css`
- `apps/web_portal/templates/demo/`（8個模板）
- `apps/web_portal/tests/test_demo_portal.py`
- `docs/coordination/tasks/TASK-012.md`
- `docs/coordination/reports/TASK-012-CODEX.md`
- `docs/coordination/HANDOFF.yaml`

原有未追蹤檔案 `apps/web_portal/static/images/logo_square.png` 只被模板引用，未被本任務修改。
