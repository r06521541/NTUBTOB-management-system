# TASK-072：整合 Phase C repository readiness 成果

## 任務目標

將已完成並經 Work 驗收的 Phase C production migration readiness 成果，透過描述性 PR、required CI 與 squash merge 正式整合進 `main`，為後續獨立的 production migration execution task 鎖定可引用的 exact merged commit。

## 背景與現況

- `origin/main` 目前位於 `027b6b8`。
- 本機已完成並驗收 TASK-071；Work 接受的實作 commit 為 `e979cd61f6a2473bc819da3ea4304784b1f19935`，結案 commit 為 `f458088`。
- Work 已獨立驗證三個 verifier、compile check、`git diff --check` 與 localhost-only PostgreSQL 16 完整 155 項測試。
- GitHub CLI 於任務開始時回報既有登入 token 無效；push／PR 前須由 Owner 在自己的終端完成 `gh auth login -h github.com`，不得把 token 或驗證碼貼入 repository 或對話。

## 工作範圍

1. 使用 `codex/task-072-phase-c-repository-integration` branch。
2. 確認 PR diff 僅包含 TASK-071 readiness package 與必要協作文件。
3. Push branch，建立描述性 PR，等待 required CI。
4. CI 成功且無新增 blocking finding 後，依一般 Git 工作流程長期授權將 PR 標記 ready 並 squash merge。
5. 唯讀確認 merged commit、PR 與 `main` 狀態；不為單純 merge metadata 再建立 closeout commit。

## 非目標與安全限制

- 不連線或修改 production Supabase。
- 不執行 `0003 -> 0004` migration、DDL、DML、backup 或 restore。
- 不部署任何 service，不開啟 runtime／identity-maintenance flags。
- 不操作 Secret、IAM、Scheduler、Cloud resources，亦不發送 LINE／Discord 通知。
- 不修改 Phase C application、migration 或 readiness contract；若 CI 暴露實質問題，停止 merge 並另行補正。

## 驗收條件

- PR title 能在離開 TASK 文件時理解 Phase C readiness 的成果。
- PR diff 與 `origin/main` 比較無非預期或敏感檔案。
- required CI 全數成功。
- 使用 squash merge，`main` 只保留一個描述性整合 commit。
- 合併後仍未發生 production database、deployment 或 runtime mutation。

## 驗證命令

```powershell
git diff --check origin/main...HEAD
git status --short
gh pr checks <PR-number>
gh pr view <PR-number>
```

## Base commit

`027b6b8`
