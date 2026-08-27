# TASK-160 Web Portal 登入與管理流程清理

## Classification

- task_type: delivery
- risk: L2 session／CSRF／identity maintenance presentation
- delivery_group: `web-portal-reliability-202608`
- requires_independent_pr: true
- authority_branch: `codex/task-160-web-portal-cleanup`
- repository_authority: `305ed4b3d6bb8d2954e944eb13af17f5994e4e9f`
- production_or_real_data: prohibited

## Completed writer claim

- role: `codex-writer`
- claim_id: `task-160-web-portal-cleanup-writer-20260827`
- lease_version: 1
- actor_id: `codex-writer:task160-web-portal-cleanup`
- state: `completed`
- implementation_commit: `29ae8e2d064ed823af479e82e59f657a1916364d`
- scope: repository-only Web Portal reliability and management UX cleanup
- owned paths:
  - `apps/web_portal/app.py`
  - `apps/web_portal/templates/dashboard.html`
  - `apps/web_portal/templates/identity_admin.html`
  - `apps/web_portal/templates/person_list.html`
  - `apps/web_portal/static/production_portal.css`
  - `apps/web_portal/tests/test_admin_security.py`
  - `apps/web_portal/tests/test_brand_ui.py`
  - `docs/coordination/tasks/TASK-160.md`
  - `docs/coordination/reports/TASK-160-CODEX.md`
- write: exact task branch and owned paths only; commit/push handoff authorized; Main owns final review/PR/merge
- report_to: `main-work`
- stop_conditions: need for schema/migration, production/runtime/Secret/cloud access or mutation, LINE provider change, weakening state/nonce/CSRF, ambiguous identity eligibility, unexpected dirty-state overlap

## Product outcome

一次收斂 Owner 實際操作發現的 Web Portal friction：電腦瀏覽器 LINE 登入必須由按鈕建立乾淨且同瀏覽器綁定的新 OAuth transaction；Dashboard 賽事回覆可正常通過 CSRF；人員管理預設只顯示 active；待配對 LINE identity 能清楚選擇 eligible 既有 Member；同一天賽事在 Dashboard 視為同一日程群組。

## Required behavior

1. `mode=browser` 只在電腦瀏覽器入口清除舊的 Portal／OAuth session state，再建立新的 session-bound nonce/state；一般 LINE in-app 登入路徑行為不變。Callback 仍嚴格驗證 signed state、期限與 session nonce，不新增跨瀏覽器 transferable state。
2. Production Dashboard render 必須提供既有 reply forms 的 CSRF token；缺少／錯誤 token 仍 fail closed，成功 POST 沿用既有 repository 與通知語意。
3. `/manage/people` 無參數時只顯示 `active`；只有明確切換才顯示非 active，搜尋與分頁必須保留選擇。
4. Pending LINE identity 顯示明確的既有 Member chooser：只列有 Member link 且後端可接受的 active／inactive Person，提供 placeholder、空狀態與 inactive 提示；maintenance 關閉時所有 mutation controls（含 chooser）一致停用。不得依 display name 自動配對。
5. Dashboard 將首場賽事當天的其他賽事放在同一「下一個比賽日」群組，較晚日期才進入近期賽程；每場 reply form、連結與狀態維持獨立。

## Invariants and non-goals

- 不改 LINE provider、callback registration、Secret、cookie security flags、OAuth expiry 或 production runtime flags。
- 不啟用 `WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED`；正式啟用與 production deployment 仍是 Owner exact gate。
- 不修改 schema、Member／Person／Identity domain semantics、通知決策或正式資料。
- 不改 LINE in-app browser 的既有順暢流程。
- 本 task 不以 repository tests 宣稱 production 已部署或已由真人驗收。

## Verification budget

- 先新增可重現五項行為的 focused regressions，再實作。
- Writer 執行 Web Portal affected complete suite、格式／compile、`git diff --check`、scope/status review。
- 初版 diff 後由一位獨立 Auth／Identity reviewer 檢查 session、CSRF、eligible target、maintenance fail-closed 與資料不洩漏。
- Main 做實際 diff 與關鍵 regressions 驗收；final PR 使用一次 change-selected hosted CI。
- 不使用 browser/provider、production data、cloud、runtime、Secret、emulator 或 deployment。

## Acceptance status

- Writer affected complete：212 passed／2 Windows platform skips。
- Independent Auth／Identity correction review：ACCEPT；無 blocking finding。
- Main targeted `test_admin_security.py`：116 passed。
- Repository implementation accepted；等待 single final PR hosted gate，尚未部署。
