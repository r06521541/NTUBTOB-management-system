# TASK-004：修正賽程隊伍篩選，避免混入非本隊比賽

狀態：`ready_for_codex`
優先級：P1
建立者：Work
`base_commit`：`da7256e9a9698838b80e22f80d6ff593fcc9e56f`
PR 工作包授權：`approved`

## 1. 任務目標

修正 `functions/update_game_schedule/main.py` 的賽程篩選錯誤，確保回傳結果同時符合「本隊參賽」與「指定時間範圍」兩個條件，避免其他球隊賽事進入新增、取消比對及後續通知流程。

## 2. 已確認背景

- `game_crawl(team_name, start_time, end_time)` 先從 crawler 結果建立 `game_list`。
- 第一個 list comprehension 正確從 `game_list` 篩選主場或客場為 `team_name` 的賽事。
- 第二個 list comprehension 又從原始 `game_list` 篩選日期，而不是從已完成隊伍篩選的 `games` 繼續篩選。
- 因此前一個隊伍條件被覆蓋，時間範圍內的其他球隊賽事可能被回傳。
- `update_game_schedule` 目前沒有 repository tests。
- 現有 Python 3.10 CI 已執行 game broadcast 17 tests 與 notify cron 4 tests，沒有安裝 application dependencies。

## 3. 行為規則

- 賽事只要 `home_team == team_name` 或 `away_team == team_name` 即視為本隊賽事。
- 隊名使用目前的完全相等比較；本任務不新增模糊比對、別名或正規化。
- `start_time` 與 `end_time` 皆為包含邊界：`start_time <= game.start_datetime <= end_time`。
- 同時符合隊伍與時間條件才可回傳。
- 保留 crawler 原始順序。
- 空輸入回傳空 list。
- 測試使用 timezone-aware datetime，不新增或改變時區轉換規則。

## 4. 工作範圍

1. 抽出不依賴 Flask、Functions Framework、資料庫、crawler 或通知 SDK 的純篩選 helper。
2. helper 接收已建立的 game-like objects、`team_name`、`start_time` 與 `end_time`，回傳同時符合兩項條件的 list。
3. `game_crawl()` 在完成 crawler response 與 `Game.from_dict()` 後呼叫該 helper。
4. 不改變 crawler 呼叫、Game 解析、錯誤通知或 handler response 行為。
5. 新增可在無 application dependencies 的環境執行的離線 unit tests。
6. 更新 Python 3.10 GitHub Actions workflow，加入 `update_game_schedule` test suite。
7. 建立 Codex report，依流程完成描述性 commit、push 與 Draft PR。

## 5. 明確非目標

- 不呼叫正式 crawler、資料庫、Discord、LINE、weather 或其他外部 API。
- 不執行 Cloud Functions deploy、Cloud Build 或任何 GCP 操作。
- 不修改 Secret、環境變數、IAM、Cloud Scheduler 或 production data。
- 不修改目前的 `settings.current_team` 值。
- 不新增隊名 alias、trim、大小寫或 Unicode 正規化規則。
- 不修改新增／取消賽事的 database 比對邏輯。
- 不處理 `game_crawl()` 其他可能的錯誤處理或回傳型別問題。
- 不修改 Web Portal UI、notify cron、game broadcast 或 shared models。
- 不進行大型重構。

## 6. 驗收條件

- [ ] 範圍內且本隊為主場的賽事被保留。
- [ ] 範圍內且本隊為客場的賽事被保留。
- [ ] 範圍內但雙方皆非本隊的賽事被排除。
- [ ] 本隊賽事若早於 `start_time` 或晚於 `end_time` 會被排除。
- [ ] 剛好等於 `start_time` 或 `end_time` 的本隊賽事會被保留。
- [ ] 空 list 回傳空 list。
- [ ] 混合 fixture 的回傳順序與輸入順序一致。
- [ ] `game_crawl()` 不再以原始 `game_list` 覆蓋隊伍篩選結果。
- [ ] 測試完全離線，不 import 或呼叫 crawler、DB、LINE、Discord 或 GCP。
- [ ] 既有 game broadcast 17 tests 全部通過。
- [ ] 既有 notify cron 4 tests 全部通過。
- [ ] 新增 schedule filter tests 全部通過。
- [ ] GitHub Actions 在 Python 3.10 執行三個 suites，且不新增 secret、write permission、dependency install、deploy 或 publish。
- [ ] `git diff --check` 通過，diff 限於任務與協作文件範圍。

## 7. 必要測試

```text
python -m unittest discover -s apps/game_broadcast_service/tests -v
python -m unittest discover -s apps/notify_cronjob_service/tests -v
python -m unittest discover -s functions/update_game_schedule/tests -v
git diff --check
git status --short
```

Work 驗收時另需：

- 查驗實際 `main.py` 與 pure helper diff。
- 以 mutation 或等價方式證明：若時間篩選重新從未經隊伍篩選的原始 list 開始，測試會失敗。
- 使用 GitHub CLI 查驗 Draft PR、Python 3.10 runtime 與三個 suites 的 job log。

## 8. 安全限制

- 測試 fixture 必須匿名化，只使用明顯假的隊名與賽事資料。
- 不讀取任何 `.env.yaml` 或 Secret value。
- 不使用真實球員、LINE user、比賽 ID 或正式資料庫資料。
- 不得為測試方便而降低 authentication、加入 GitHub Secret 或安裝不必要 dependency。
- 發現任務需要 schema、部署、Secret、正式通知或重大架構變更時，立即停止並交回 Owner。

## 9. 預計影響檔案

- `functions/update_game_schedule/main.py`
- `functions/update_game_schedule/game_filter.py`（名稱可依鄰近風格微調，但必須保持純函式與無外部依賴）
- `functions/update_game_schedule/tests/__init__.py`
- `functions/update_game_schedule/tests/test_game_filter.py`
- `.github/workflows/python-tests.yml`
- `docs/coordination/reports/TASK-004-CODEX.md`
- `docs/coordination/HANDOFF.yaml`

不應修改 requirements、shared library、database model/schema、deployment config 或其他服務。

## 10. 已知風險與假設

- 本任務假設 crawler 回傳的 `home_team`、`away_team` 與 `start_datetime` 已由 `Game.from_dict()` 正確解析。
- 目前採完全相等隊名比較；若資料來源存在「臺大校友」「臺灣大學」等別名，需另立產品規則與任務。
- 此修正避免錯誤賽事進入後續流程，但不驗證 production crawler response 或既有 database 中是否已有錯誤資料。
- 新 tests 只驗證純篩選行為，不代表 Cloud Function 線上整合正確。

## 11. Git 與 PR 規格

- 建議 branch：`codex/fix-schedule-team-filter`
- Implementation commit／PR title：`fix(schedule): preserve team filter when selecting games`
- TASK 編號放在 commit body/footer：`Refs TASK-004`
- 後續 report/review commit 也必須描述實際內容，不得使用 `hand off TASK-004` 或 `update TASK-004` 作為標題。
- Owner 已批准 DEC-004 定義的 PR 工作包；不包含 merge、部署或其他永久排除操作。

## 12. Owner 決策

Owner 已於 2026-08-04 批准 TASK-004 與 PR 工作包。

此授權包含 task branch、範圍內 commits、push、Draft PR、CI 查驗與同一 PR 的驗收文件更新；不包含 merge、部署、Secret 操作、正式通知、不可逆資料操作或重大架構變更。

## 13. Codex 完成要求

Codex 完成後必須：

1. 建立 `docs/coordination/reports/TASK-004-CODEX.md`。
2. 記錄實際修改、完整測試摘要、未執行項目、風險與外部影響聲明。
3. 使用描述性 commit title，將 TASK 編號放在 body/footer。
4. 建立 branch、commit、push 與 Draft PR，等待 Python 3.10 CI。
5. 更新 `HANDOFF.yaml` 為：
   - `status: ready_for_review`
   - `next_actor: work`
6. 不得 merge、deploy、操作 Secret、發送通知或修改正式資料。
