# TASK-037 Codex 完工報告

更新時間：2026-08-06（Asia/Taipei）

## 任務狀態

- 狀態：`ready_for_review`
- Branch：`codex/task-036-deploy-roster`
- Base commit：`fee79c9`
- Implementation commit：`bfa5494`
- 未 push、未建立 PR、未 merge、未部署

## 實作結果

- LINE callback 只把必要的 `user_id` 與 `member_id` 寫入 signed cookie session；LINE profile 的 `displayName` 仍依既有安全契約驗證，但不再保存。
- 每次 request 精確移除舊 session 的 `member` 與 `display_name`，不使用 `session.clear()`；既有 identity、OAuth nonce、return path、CSRF 與 demo keys 都保持不變，使舊 session 在下一次 request 平順重簽。
- `/attendance` 先沿用 `member_required` 驗證 opaque identity，再以 `member_id` request-time 查詢 fresh Member；找不到 Member 時只清除 `user_id`／`member_id`，回覆安全的 403 等待核可頁，且不查 Game、attendance 或發出 HTTP。
- 畸形 session 在 Member lookup 前 fail closed；既有 LINE OAuth state、cookie policy、demo、roster 與 admin 行為未更動。
- README 已記錄最小 session payload、legacy migration 與 attendance rehydration 行為。

## 變更檔案

- `apps/web_portal/app.py`
- `apps/web_portal/tests/test_admin_security.py`
- `apps/web_portal/README.md`
- `docs/coordination/reports/TASK-037-CODEX.md`
- `docs/coordination/PROJECT_STATE.md`
- `docs/coordination/HANDOFF.yaml`

## 驗證

本機全域 `python` 不存在，`py -3.10` 指向已不存在的 WindowsApps runtime；workspace dependency loader 未能回傳 bundled runtime，因此以已安裝且具專案依賴的 Python 3.9 執行行為測試，並另以 AST `feature_version=(3, 10)` 驗證 Python 3.10 grammar：

```text
py -3.9 -m unittest discover -s apps/web_portal/tests -v
Ran 65 tests — OK (skipped=2)

py -3.9 -m compileall -q apps/web_portal
OK

ast.parse(..., feature_version=(3, 10))
Python 3.10 grammar OK

py -3.9 tools/deploy_web_portal.py
Preflight passed; no cloud or HTTP commands were run.

git diff --check
OK
```

兩項 skip 是既有 Windows 缺少 Unix `make`／`sh` 的 deployment contract coverage，與本次變更無關。部署 dry-run 在實作尚未 commit 時先依設計因 dirty worktree fail closed，建立本機實作 commit後於乾淨狀態重跑通過。

## 未驗證與限制

- 尚未由實際 Python 3.10 interpreter 或 GitHub hosted runner 執行完整 suite；Python 3.10 grammar 已離線通過，PR CI 仍需另行授權。
- 未使用真實瀏覽器、LINE、production DB 或 Cloud Run；離線測試不能證明 production cookie migration 或 Member lifecycle 整合。
- 未讀取 `envs/**/.env.yaml` 或 Secret，未執行 gcloud／HTTP／通知，未修改 schema、shared library、IAM、Secret、cache 或其他服務。
- 未 push、開 PR、merge 或部署；以上動作均需 Owner 另行批准。
