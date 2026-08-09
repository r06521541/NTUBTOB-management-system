# TASK-035 Codex 實作報告

更新時間：2026-08-06（Asia/Taipei）

## 任務狀態

- 狀態：`ready_for_review`
- Branch：`codex/protect-game-roster`
- Base commit：`d5c4a2f48499c4d1646fe9e56b0d27dfe58c82de`
- Implementation commit：`3038e3b`
- Draft PR：[PR #44](https://github.com/r06521541/NTUBTOB-management-system/pull/44)

## 完成內容

- 新增共用 `member_required` guard，只接受非空字串 `user_id` 與非 bool 的正整數 `member_id`。
- `/game-roster/<int:game_id>` 在任何 Game、attendance、Member 或 HTTP 查詢前拒絕匿名及畸形 session，並以安全站內 path 導向既有登入入口。
- 合法已配對會員保留既有名單內容；不存在的 game 明確回覆 404，且不再執行 attendance 查詢。
- README 明確記錄目前是會員邊界，不代表已完成普通隊員／幹部／系統管理者的 RBAC 分級。

## 測試與驗證

- GitHub Actions run `31060596934`／job `92487531997`：Python 3.10 unittest suite 通過。
- 新增離線案例涵蓋匿名、缺欄位、錯誤型別、bool／非正整數 Member ID、空白 user ID、合法會員與不存在 game。
- 測試確認拒絕路徑不查 Game、attendance、Member，且不發出 HTTP request。
- `git diff --check`：通過。
- 本機 `python` 指令不存在，`py -3.10` 指向已移除的 Windows Store runtime，因此 Python 3.10 實跑證據來自 hosted runner。

## 安全聲明

- 未連線 production DB、LINE、Discord 或其他外部 API；測試全部使用 mock／fake model。
- 未修改 schema、migration、Secret、IAM、Cloud Run、部署設定或其他服務。
- 未 merge、部署或發送正式通知。

## 變更檔案

- `apps/web_portal/admin_security.py`
- `apps/web_portal/app.py`
- `apps/web_portal/tests/test_admin_security.py`
- `apps/web_portal/README.md`
- `docs/coordination/reports/TASK-035-CODEX.md`
- `docs/coordination/PROJECT_STATE.md`
- `docs/coordination/HANDOFF.yaml`
