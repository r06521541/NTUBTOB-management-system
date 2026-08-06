# TASK-035 Work 驗收報告

驗收時間：2026-08-06（Asia/Taipei）

## 結論

- 結果：`accepted`
- Branch：`codex/protect-game-roster`
- Base：`d5c4a2f48499c4d1646fe9e56b0d27dfe58c82de`
- Implementation：`3038e3b`
- Codex completion：`45079c0`
- Draft PR：[#44](https://github.com/r06521541/NTUBTOB-management-system/pull/44)
- 下一位角色：Owner（決定是否 ready 與 squash merge；deployment 仍須另行批准）

## 驗收結果

- 新增的 `member_required` 只接受非空白字串 `user_id` 與非 bool 的正整數 `member_id`。
- `/game-roster/<int:game_id>` 在任何 Game、attendance、Member 或 HTTP 查詢前驗證會員 session；匿名、缺欄位及畸形型別均 redirect 至既有登入入口。
- Return target 使用 `request.path`，只包含站內 path，不把外部 host 或不可信 query 帶入 OAuth 流程。
- 合法已配對會員仍可查看既有 roster 內容；本任務沒有擅自決定普通隊員、幹部與管理者間的細部可見規則。
- Game 不存在時回覆 404，且不查 attendance，避免原本可能的 `None.id` 500。
- `admin_required`、管理 allowlist、CSRF、LINE Login 與 demo route 測試均維持通過。

## Work 獨立驗證

```text
Web Portal tests: 61 passed, 2 existing Windows make/sh skips
compileall apps/web_portal: passed
Web Portal deployment dry-run: passed; no cloud or HTTP
git diff --check d5c4a2f..HEAD: passed
working tree before review docs: clean
GitHub Python 3.10 CI run 31060680146 / job 92487791860: success
PR #44: open, Draft, mergeable
```

## 尚未驗證與風險

- 測試使用 fake models／mock，不代表 production DB 或真實 LINE Login 已驗證；本任務未存取 production。
- 會員 session 的 `member_id` 只證明登入 callback 曾完成配對，request-time 不重新確認 Member 是否已停用或移除；目前 schema 亦無正式 account approval／role 狀態。這應與後續 RBAC／member lifecycle 設計一起處理。
- 已登入普通隊員目前仍可看未回覆者姓名；此為明確保留的產品待決策，不是本任務遺漏。
- PR #44 也包含尚未合併至 main 的 TASK-034 closeout 與 TASK-035 planning／approval 文件；沒有額外程式行為。
- 本次未部署，未修改 Secret、IAM、DB、schema、data 或 LINE／Discord 通知。

## 建議

接受 TASK-035，可將 PR #44 標記 ready 並以 squash merge 合併。若要讓 production 隱私邊界生效，merge 後仍須以 exact main commit 與當時的 100% traffic revision另行批准 Web Portal deployment。
