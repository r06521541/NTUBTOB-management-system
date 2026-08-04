# TASK-004 Work 驗收報告

驗收時間：2026-08-04T22:35:47+08:00
驗收者：Work
驗收結論：`accepted`
下一位角色：`owner`

## 1. 驗收基準

- branch：`codex/fix-schedule-team-filter`
- task base：`da7256e9a9698838b80e22f80d6ff593fcc9e56f`
- implementation：`11e96361db0158c47a82de1c1ebf87ca9a20bcec`
- Codex evidence：`0b0450f678d429b907051f6bc8006f55cfad2a69`
- Codex handoff：`8f485bf46b13628d72cb27a62dba6779d3cc2fa7`
- Draft PR：[#28](https://github.com/r06521541/NTUBTOB-management-system/pull/28)
- Work 已直接查驗實際 diff、commits、程式碼、tests、PR 與最新 CI job log，沒有只依賴 Codex report。
- 驗收前唯一額外狀態為 Owner 的未追蹤 Web Portal 圖片目錄；TASK-004 未修改或納入該資產。

## 2. 實際修改查驗

- 新增 `filter_games()` 純函式，同時套用完全相等的主／客隊條件與包含起訖邊界的時間條件。
- `game_crawl()` 在 crawler 資料轉為 `Game` 後呼叫純函式，不再從原始 `game_list` 重做日期篩選而覆蓋隊伍條件。
- helper 只依賴標準函式庫 `datetime` 與 `typing`，沒有 Flask、資料庫、crawler 或通知依賴。
- 新增 5 個離線 tests，涵蓋主客場、非本隊、範圍外、兩側邊界、空輸入與順序。
- Python 3.10 workflow 新增 schedule suite，維持 `contents: read`，沒有新增 Secret、dependency install、deploy 或 publish。
- 沒有修改 requirements、shared library、database model/schema、migration、deployment config、環境變數或 Secret。

## 3. 驗收結果

| 驗收條件 | 結果 | 證據 |
| --- | --- | --- |
| 本隊主場與客場賽事均保留且維持順序 | 通過 | `test_keeps_home_and_away_games_in_input_order`。 |
| 範圍內非本隊賽事被排除 | 通過 | `test_excludes_other_teams_even_when_game_is_in_date_range`。 |
| 範圍外本隊賽事被排除 | 通過 | `test_excludes_team_games_outside_date_range`。 |
| 起訖時間包含邊界 | 通過 | `test_includes_both_date_boundaries`。 |
| 空輸入回傳空 list | 通過 | `test_empty_input_returns_empty_list`。 |
| 原錯誤型 mutation 可被辨識 | 通過 | Work 模擬只套用日期條件，會錯誤保留範圍內非本隊賽事。 |
| 三套本機 tests | 通過 | schedule 5/5、game broadcast 17/17、notify cron 4/4。 |
| Python 3.10 CI | 通過 | 最新 HEAD run `30919277284` 使用 CPython 3.10.20，三套 tests 全數通過。 |
| Workflow 安全邊界 | 通過 | 最新 job 顯示 `Contents: read`，沒有外部副作用步驟。 |
| Diff 與任務範圍 | 通過 | `git diff --check da7256e..HEAD` 無錯；implementation 限於指定程式、tests 與 workflow。 |

## 4. Work 獨立證據

```text
bundled Python 3.12.13
update_game_schedule: Ran 5 tests — OK
game_broadcast_service: Ran 17 tests — OK
notify_cronjob_service: Ran 4 tests — OK
Python 3.10 grammar parse: OK
git diff --check: OK
```

Mutation 等價檢查使用一筆範圍內非本隊賽事與一筆範圍內本隊賽事；正確 helper 只回傳本隊賽事，僅日期條件的 mutant 會回傳兩筆。

GitHub Actions 最終證據：run `30919277284`、job `92025325144`、head `8f485bf46b13628d72cb27a62dba6779d3cc2fa7`、CPython `3.10.20`、結論 `SUCCESS`；17、4、5 tests 全數通過。

## 5. 回歸風險與限制

- 測試隔離純篩選行為，沒有驗證 production crawler response、`Game.from_dict()`、資料庫內容或 Cloud Function 線上整合。
- 隊名仍採完全相等；alias、空白、大小寫或 Unicode 差異不在本任務範圍。
- 本修正不清理資料庫中可能已存在的錯誤賽事。
- 未執行 Cloud Build、deploy、staging smoke test 或任何 GCP 操作。
- Black／isort 未執行；Work 已檢查 diff 與 Python 3.10 grammar。

## 6. Blocking 問題

無。

## 7. 驗收結論

`accepted`

TASK-004 已修正日期篩選覆蓋隊伍條件的資料正確性錯誤，並具備離線回歸 tests 與 Python 3.10 hosted runner 證據。建議 Work review push 後等待最終 CI 成功，再由 Owner 決定是否將 PR #28 標記 ready 並 merge。

此結論不批准部署、Secret 操作、正式 LINE／Discord 通知、production data 操作或不可逆變更。
