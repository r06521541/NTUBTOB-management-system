# TASK-094 Codex report

## Implementation

- `/future-games` 改用正式 portal tokens、`member_portal.css`、共用導覽與 mobile-first empty state；資料仍來自 `Game.search_between`／`Game.get_games_in_this_week_and_month`。
- `/game-roster/<game_id>` 與 `/attendance` 已保留正式 `Game`／`Member`／attendance callers，並驗證既有 shared mobile styles；未改 `/demo/*`、domain/schema 或規則。

## Route → data flow matrix

| Route | Caller/data source | Template/read behavior | Success/empty/error/denied test |
| --- | --- | --- | --- |
| `/future-games` | `Game.search_between` → `Game.get_games_in_this_week_and_month` | `future_games.html` renders week/month cards and empty state | `test_future_games_uses_game_repository_and_renders_empty_state`; caller mock verifies repository read |
| `/game-roster/<game_id>` | `Game.search_by_id` → `attendance_for_game` → `process_replies` | `game_roster.html` renders roster/name-style controls and unanswered count | `test_valid_member_session_hides_unanswered_names_on_roster`; `test_missing_game_returns_404_without_attendance_query`; invalid session tests deny before query |
| `/attendance` | `phase_c_repository.resolve_line_principal` or `Member.search_by_id`; `Game.search_for_invited`; `attendance_for_game` | `attendance.html` renders readback groups and roster links | `test_attendance_reloads_games_and_replies_on_every_request`; malformed identity/unauthenticated/error tests |

## Verification

- Web Portal unittest：133 passed、2 skipped。
- `py_compile`、`git diff --check` 通過。
- 未執行 production、deploy、schema、Secret、IAM、Scheduler、正式 DB 或真實通知；未做 browser/LINE smoke。
- Black/isort 逐檔檢查將於交棒前完成；不宣稱 browser-pixel QA。
