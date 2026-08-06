# TASK-042 Codex 完工報告

更新時間：2026-08-06（Asia/Taipei）

## 任務狀態

- 狀態：`ready_for_review`
- Branch：`codex/deploy-task-040`
- Base commit：`ad17ac7908ed833fba1827364fb87e72e1ed4b06`
- Implementation commit：`769f846`
- 未 push、未建立 PR、未 merge、未部署

## 實作結果

- 新增 member-only `/account`，每次依 session `member_id` 重新查詢 Member，只顯示姓名、LINE 登入方式及 policy 解析的 Portal 角色。
- allowlist admin 顯示「系統管理者」及 Member 配對入口；一般隊員不顯示，既有 server guard 仍為真正授權邊界。
- 新增 POST-only `/logout`，使用獨立且 session-bound 的 CSRF token，以 constant-time 比較驗證；成功後 `session.clear()`，錯誤 token 不修改 session。
- account、attendance、game roster 共用本機 CSS 與手機可橫向容納的最小會員導覽。
- Demo 明確阻擋 production account/logout，即使 session 被人工塞入 production-like identity 仍回傳 404。
- 更新 Web Portal README 與 route access matrix；未新增 production officer 來源。

## 驗證

使用 bundled CPython 3.12.13 執行：

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 89 tests — OK (skipped=2)

python -m compileall -q apps/web_portal
OK

Python 3.10 AST grammar check
18 Python files — OK

git diff --check
OK
```

兩項 skip 為既有 Windows 環境缺少 Unix `make`／`sh` 的 deployment contract coverage。

## 安全與範圍確認

- 缺失或畸形 identity 在 Member query 前 fail closed；Member 不存在時只清除 authenticated identity，且不進入 game／attendance／HTTP 呼叫。
- logout CSRF 與 Member 配對 CSRF 分離；成功登出會清除 identity、OAuth 暫存、兩種 CSRF 與 Demo session keys。
- 未修改 schema、model、environment、dependency、OAuth、cookie、deployment 或其他服務。
- 未讀取 `.env.yaml`／Secret，未連線 production DB、LINE 或其他外部服務，未發通知。

## 尚未驗證

- hosted Python 3.10 CI 留待 TASK-041＋TASK-042 PR 工作包。
- 尚未執行 375px 實體瀏覽器視覺驗收；CSS 與 navigation route 契約已由離線測試驗證。
- LINE provider 登入狀態不會被 Portal logout 撤銷，UI 與 README 已明確說明。
