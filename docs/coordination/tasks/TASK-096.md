# TASK-096：Phase D Web Portal UI refresh

task_type: delivery
delivery_group: phase-d-web-ui-refresh
requires_independent_pr: true
status: completed
owner: work
codex: codex

整併說明：本 task 吸收原 TASK-095 的 Game dashboard／正式賽程頁面範圍；TASK-095 不再作為獨立
delivery group 或 PR 單位。TASK-096 是本成果唯一的 delivery task。

## 目標

將 Demo 的 mobile-first 視覺語言與資訊架構帶入正式 Web Portal，讓現有 schema、Game／Attendance／Person／Account
contracts 能以一致、可操作、可驗收的正式頁面提供使用者使用。

## 範圍

- 共用正式 Portal shell、navigation、card、badge、form、empty／error state 與 responsive behavior。
- Member Dashboard、Schedule、Game detail、本人出席回覆、Attendance summary 與 Roster。
- Account、Person directory、Person detail、Qualification 摘要與 Identity review UI。
- 沿用既有 Game／attendance reply／Phase C Person repository；不新增 schema。
- 以既有 1–5 attendance reply semantics 支援本人回覆，不新增 Demo-only arrival、交通、裝備或備註欄位。
- 補 route access、CSRF、mobile viewport、accessibility-oriented 與 template contract tests。

## 非目標

- 不建立或切換 Event／Activity production routes。
- 不建立正式 officer workspace、通知偏好、交通、checklist、season statistics 或新的登入 provider。
- 不修改 schema、migration、production data、allowlist、Secret、IAM、Scheduler 或 cloud resources。
- 不啟用 `WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED`，不執行 production deployment、人工 smoke 或真實通知。

## 驗收條件

- 正式 Game／Attendance／Person／Account 頁面使用一致的 local Demo-style UI，375px mobile 與 desktop 均可操作。
- Game detail 與本人 attendance reply 使用既有資料 contract；成功、空資料、取消、錯誤、未登入與無權限狀態有明確回饋。
- Person／Identity／Qualification mutation UI 維持既有 capability、CSRF 與 flag-off boundary；不以 UI 隱藏取代 authorization。
- 正式 templates 不依賴外部 CDN；敏感資料邊界不退化。
- 完成受影響 Web Portal unittest、route/template/accessibility checks、Python compile／format check、`git diff --check`。

## Execution checkpoint

已於 2026-08-10 由 Codex 回報；原 TASK-095 的 Game dashboard 範圍已併入本 delivery，文件入口已統一。
