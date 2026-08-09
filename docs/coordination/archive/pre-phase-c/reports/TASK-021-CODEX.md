# TASK-021 Codex Implementation Report

日期：2026-08-05
狀態：`ready_for_review`
PR：[Draft PR #35](https://github.com/r06521541/NTUBTOB-management-system/pull/35)

## Git 範圍

- Task base：`c022d5185cf6126ffd228b0c95b815c80ee39606`
- Branch 起點包含 Owner 已批准的 TASK-021 規劃與授權 commits：`4275e57`、`7dd8da3`
- Implementation commit：`1f0813e00ac22464d099aa136bc3a63b6d002e19`
- Branch：`codex/protect-web-portal-member-matching`

## 完成內容

- 三個成員配對管理 route 共用 LINE session 與 Member ID allowlist guard。
- `WEB_PORTAL_ADMIN_MEMBER_IDS` 僅接受不重複的逗號分隔正整數；缺失、空白或任一格式錯誤均整體 fail closed。
- LINE callback 在既有 session 內容之外記錄最小的 `member_id`，供 server-side authorization 使用。
- 未登入者導向既有登入流程；非管理者與無效設定回 HTTP 403，且在管理資料查詢前拒絕。
- 管理頁建立並重用不可預測的 session CSRF token；兩個 POST 以 constant-time comparison 驗證，失敗回 HTTP 400 且在 ORM／通知前拒絕。
- 合法 match、ignore、redirect 與 match 成功 Discord 通知契約維持不變。
- 新增 fake ORM／notifier 的離線 route tests、設定範例、README 與 Python 3.10 CI step。

## 驗證結果

本機 CPython 3.9.13（本機 Python 3.10 launcher 指向已不存在的 WindowsApps runtime）：

- Web Portal：19/19 通過。
- LINE webhook ingress：10/10 通過。
- Game broadcast：28/28 通過。
- Notify cronjob：9/9 通過。
- Update schedule：5/5 通過。
- Scheduled deployment wrapper：11/11 通過。
- `python -m compileall -q apps/web_portal`：通過。
- `git diff --check`：通過。

GitHub Actions run `30988641134`／job `92249235302`：

- Python 3.10 unittest suite：`SUCCESS`（18 秒）。
- Workflow parser、Python 3.10 runtime 與新增 Web Portal suite 均已實跑。

## 安全邊界

- Route tests 在載入 app 前注入 fake ORM、Discord notifier 與 attendance modules；沒有 production DB、LINE、Discord 或其他網路呼叫。
- 僅更新非機密 `.env_example.yaml`，未讀取 `.env.yaml` 或 Secret。
- 未部署、呼叫 production、發送通知、操作 production DB、Secret、IAM、Scheduler 或 schema。
- PR 保持 Draft，未 ready 或 merge。

## 未驗證與殘餘風險

- 尚未設定或驗證 production 的 allowlist；未設定時會安全鎖住所有管理者。部署與 runtime 設定需另行精確授權。
- 未向真實 LINE Login 或 production Web Portal 發 request；線上 session／runtime 行為待未來部署後驗證。
- 既有 session 仍保存完整 `member` 物件，未依本任務非目標重構；本次只新增可授權的最小 `member_id`。
- Safe redirect、session lifetime、logout、rate limiting 與 audit log 均不在本任務範圍。

## 變更檔案

- `.github/workflows/python-tests.yml`
- `apps/web_portal/README.md`
- `apps/web_portal/admin_security.py`
- `apps/web_portal/app.py`
- `apps/web_portal/templates/match_member.html`
- `apps/web_portal/tests/test_admin_security.py`
- `envs/web_portal/.env_example.yaml`
- `docs/coordination/reports/TASK-021-CODEX.md`
- `docs/coordination/tasks/TASK-021.md`
- `docs/coordination/HANDOFF.yaml`
