# TASK-041 Codex 完工報告

更新時間：2026-08-06（Asia/Taipei）

## 任務狀態

- 狀態：`ready_for_review`
- Branch：`codex/deploy-task-040`
- Task base commit：`62d2de4`
- Implementation base commit：`9085a4e`
- Implementation commit：`5f9211f`
- 未 push、未建立 PR、未 merge、未部署

## 實作結果

- 新增純 Python、fail-closed 的角色與 capability policy，集中定義 `member`、`officer`、`admin` 的能力繼承。
- production principal 只可能由有效配對 session 解析為 `member`，或由完整有效的既有 admin allowlist 解析為 `admin`；沒有任何 production officer 來源。
- 既有 `member_required` 與 `admin_required` 改由集中 policy 執行，保留匿名 redirect、已登入但權限不足 403，以及 mutation 前 authorization／CSRF 邊界。
- Demo 可在登入頁明確選擇三種角色；member 看不到也無法進入幹部功能，officer 與 admin 依 `manage_events` capability 存取相同的 session-only 原型。
- Demo 導覽與 server-side route guard 共用 capability 判斷，不以隱藏 UI 代替授權。
- 新增 production／Demo route access matrix，並同步 Web Portal README。

## 修改檔案

- `apps/web_portal/role_policy.py`
- `apps/web_portal/admin_security.py`
- `apps/web_portal/demo_portal.py`
- `apps/web_portal/demo_events.py`
- `apps/web_portal/templates/demo/base.html`
- `apps/web_portal/templates/demo/login.html`
- `apps/web_portal/tests/test_role_policy.py`
- `apps/web_portal/tests/test_demo_events.py`
- `apps/web_portal/README.md`
- `docs/planning/WEB_PORTAL_ACCESS_MATRIX.md`

## 驗證

使用 bundled CPython 3.12.13 執行：

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 79 tests — OK (skipped=2)

python -m compileall -q apps/web_portal
OK

git diff --check
OK
```

兩項 skip 是既有 Windows 環境缺少 Unix `make`／`sh` 的 deployment contract coverage。第一輪測試有一項既有 Demo 文案斷言失敗；保留原「進入虛構 Demo」提示後完整重跑通過。

## 未驗證與限制

- 尚未由 hosted Python 3.10 runner 驗證，留待 Owner 批准的 PR 工作包。
- 尚未做瀏覽器視覺驗收；三角色 Demo 入口與 server-side access 已由 Flask test client 驗證。
- 未新增 schema、model、migration、環境變數或 dependency；officer persistence、角色指派 UI 與 audit log 仍屬後續任務。
- 未讀取 `.env.yaml` 或 Secret，未存取 production、DB、LINE、通知、Cloud Run、IAM 或其他服務。
