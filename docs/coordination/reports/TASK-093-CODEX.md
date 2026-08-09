# TASK-093 Codex report

## Implementation

- 強化 shared member portal component styles：mobile-first navigation、可觸控表單控制項、focus-visible accessibility、桌面寬度下的兩欄表單排版。
- 套用至既有 Game/賽程、Game detail、roster、attendance、Game day、交通／裝備分工等共用 portal layout；首頁僅沿用共用 tokens，未擴張功能。
- Contract coverage：`attendance.html`、`game_roster.html`、`account.html` 驗證 brand/member stylesheet 與 `_member_nav.html`；Demo `dashboard.html`、`games.html`、`game_detail.html`、`game_day.html`、`profile.html` 驗證共用 `demo/base.html`；CSS 驗證 touch controls（44px）、focus-visible、horizontal navigation。
- 保留既有 route、capability、CSRF/session 與低敏資料邊界；未引入 CDN 或 runtime dependency。

## Verification

## Functional flow matrix

| Flow | Route / caller | Read + mutation | Test evidence |
| --- | --- | --- | --- |
| 賽程列表／篩選 | `demo_portal.games` → `games_with_session_replies` | 讀取 game catalog，status/venue/view 篩選 | `test_filters_calendar_and_unknown_game`；空分類安全 |
| Game detail／回覆 | `demo_portal.game_detail`、`demo_portal.reply` | 讀取 state；CSRF POST 更新 Demo session，PRG 回讀 | `test_reply_uses_prg_and_is_reflected_across_pages`、`test_reply_validation_and_csrf_fail_closed`、`test_invalid_game_and_reply_fail_safely` |
| roster | `app.game_roster` → `Game.search_by_id`／`attendance_for_game` | 讀取 roster，name style allowlist | `test_roster_rejects_missing_or_invalid_member_session_before_queries`、`test_valid_member_session_hides_unanswered_names_on_roster`、`test_missing_game_returns_404_without_attendance_query` |
| attendance | `app.attendance` → fresh Member/Game callers | 讀取 games/replies，提交後回讀 | `test_attendance_reloads_games_and_replies_on_every_request`、`test_protected_attendance_round_trip_preserves_destination`、`test_attendance_malformed_identity_fails_before_member_lookup` |
| Game Day core | `demo_portal.game_day`／`update_operations` | 讀取 Game Day checklist；CSRF POST 更新 Demo session | `test_game_day_operations_are_session_only_and_resettable`、`test_game_flow_connects_schedule_detail_reply_readback_and_game_day` |
| 導航／錯誤 | demo base bottom nav、既有 login gates | return path、unauthenticated、missing/invalid fail closed | `test_unauthenticated_routes_redirect_before_queries`、`test_demo_entry_and_protected_redirect`、`test_demo_routes_fail_closed_when_gate_is_disabled` |

| Qualification management | `identity_admin_action` → `IdentityLifecycleRepository.grant_qualification`／`revoke_qualification` | dashboard summary read；POST 驗證 qualification、validity、reason、request-id，transactional audit 後 dashboard readback | `test_phase_c_admin_qualification_action_uses_transactional_repository`、`test_qualification_validity_and_revocation_fail_closed` |

矩陣使用現有 route 與 caller；未新增 Event/Activity、transport/equipment assignment、schema、production 或通知發送。未宣稱 browser-pixel QA。

## Rule source and boundary review

本次 flow 盤點以 `docs/planning/PHASE_D_QUALIFICATION_GAME_DECISIONS.md` 為唯一產品規則來源，逐項核對
`team_player`、`guest_player`、`affiliate`、`staff`、eligibility、roster/attendance、Game cancel/reschedule
與 crawler/manual ownership、notification boundary。現有 callers 的測試行為與文件規則一致；未自行新增 jersey number、
roster snapshot/override 或通知發送規則。若未來發現 caller 與決策文件衝突，應先停止該衝突範圍並交 Work review，未在本次改寫。

- Web Portal unittest：129 passed、2 skipped；py_compile、git diff --check 通過。
- Changes-requested correction 後：Web Portal unittest 130 passed、2 skipped；新增 1 組頁面／樣式 contract assertions。未宣稱實際瀏覽器像素視覺效果。
- 未執行 production、部署、正式資料或通知發送。
