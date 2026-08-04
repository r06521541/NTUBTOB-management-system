# TASK-005：在每次請求時計算賽事廣播時間視窗

狀態：`ready_for_codex`
優先級：P1
建立者：Work
`base_commit`：`c70ce63d3b91fc0d224c86a1b8f3aba085f5979c`
PR 工作包授權：`approved`

## 1. 任務目標

修正 `game_broadcast_service` 在 module import 時計算並固定目前時間的問題，確保每次邀請與取消公告請求都使用該次 request 的 Asia/Taipei 現在時間、當日開始時間及未來查詢上限，避免長壽命 Cloud Run instance 持續使用啟動時的舊時間視窗與舊寫入時間。

## 2. 已確認背景

- `apps/game_broadcast_service/app.py` 在 module import 時建立 `now`、`today_begin` 與 `ten_days_later`。
- `/invitation-announcement/trigger` 使用固定的 `now`、`ten_days_later` 查詢賽事，並以同一個固定 `now` 寫入 invitation time。
- `/cancellation-announcement/trigger` 亦使用固定視窗查詢，並以固定 `now` 寫入 cancellation announcement time。
- Cloud Run process 可以處理多次請求，因此 module import time 不等同每次 request time。
- `apps/notify_cronjob_service/app.py` 也宣告相同 globals，但目前路由與其他程式沒有使用它們。
- 現有 CI 不安裝 application dependencies；新增測試必須保持 standard-library-only，不 import Flask、LINE SDK、shared library、資料庫或通知 client。

## 3. 行為規則

- 每次 invitation 或 cancellation request 各取得一次 timezone-aware `now`。
- `now` 使用既有 `shared_module.settings.local_timezone`（Asia/Taipei）。
- `today_begin` 為該次 `now` 所在日期的 00:00:00，保留 timezone。
- 查詢上限維持既有行為：`today_begin + timedelta(days=11)`；本任務不改成 10 天或其他產品規則。
- 同一 request 的資料庫查詢與成功後寫入時間使用同一個 `now` snapshot，避免跨秒／跨日產生不一致。
- 下一次 request 必須重新取得時間，不得沿用前一次 snapshot。
- Game reminder 已在其函式內取得 request-time now，不納入本任務行為變更。

## 4. 工作範圍

1. 新增無 Flask、資料庫或通知依賴的時間視窗 helper，透過可注入 clock 取得 `now` 並回傳該次 request 所需時間值。
2. Invitation route 在 request 內取得一次 snapshot，傳給查詢及 invitation time 更新流程。
3. Cancellation route 在 request 內取得一次 snapshot，傳給查詢及 cancellation time 更新流程。
4. 調整 `mark_games_as_invited()`、`mark_games_as_cancellation_announced()` 等必要 helper，使寫入時間由 caller 明確傳入，不讀 module global。
5. 移除 `game_broadcast_service` 的 import-time 時間 globals。
6. 移除 `notify_cronjob_service` 未使用的 import-time 時間 globals 及因此不再需要的 imports；不改其 route 行為。
7. 在既有 game broadcast test suite 新增 standard-library-only tests；現有 workflow 已會自動執行該 suite，不為此新增 CI step。
8. 依協作精簡規則完成 implementation commit 與一次 Codex 完工 commit。

## 5. 明確非目標

- 不改變 11 天查詢上限、邀請規則、取消規則、提醒天數或排程頻率。
- 不修改 LINE／Discord 訊息內容、recipient、broadcast 行為或 retry 策略。
- 不呼叫正式 LINE、Discord、資料庫、crawler 或 GCP。
- 不修改 Cloud Scheduler、Cloud Run、Cloud Build、Secret、IAM、環境變數或部署設定。
- 不修改 database model/schema，不建立 migration，不清理 production data。
- 不處理 endpoint authentication、idempotency、重複排程或通知去重；這些需另立任務。
- 不進行 service 重寫或共用 library 大型重構。

## 6. 驗收條件

- [ ] 兩次 helper 呼叫若 clock 回傳不同日期，會得到各自日期的 `now`、`today_begin` 與上限。
- [ ] `today_begin` 為 local timezone 當日午夜，且 timezone-aware。
- [ ] 查詢上限精確維持 `today_begin + 11 days`。
- [ ] Invitation route 每次 request 重新取得 snapshot。
- [ ] Invitation 查詢下限與成功寫入 invitation time 使用同一個 snapshot `now`。
- [ ] Cancellation route 每次 request 重新取得 snapshot。
- [ ] Cancellation 查詢下限與成功寫入 cancellation time 使用同一個 snapshot `now`。
- [ ] `game_broadcast_service/app.py` 不再有 import-time `now`、`today_begin`、`ten_days_later`。
- [ ] `notify_cronjob_service/app.py` 不再保留未使用的 import-time 時間 globals。
- [ ] 新 tests 完全離線且 standard-library-only。
- [ ] 既有 game broadcast 17 tests、notify cron 4 tests、schedule 5 tests 全數通過。
- [ ] Python 3.10 CI 執行擴充後的 game broadcast suite，以及既有 notify cron、schedule suites；維持 read-only、無 Secret、無 deploy/publish、無 dependency install。
- [ ] Mutation 或等價檢查證明：若 snapshot 被固定於 module import 或重複呼叫不重新取時，測試會失敗。
- [ ] `git diff --check` 通過，diff 限於任務與協作文件。

## 7. 必要測試

```text
python -m unittest discover -s apps/game_broadcast_service/tests -v
python -m unittest discover -s apps/notify_cronjob_service/tests -v
python -m unittest discover -s functions/update_game_schedule/tests -v
git diff --check
git status --short
```

Work 驗收另需：

- 查驗 `app.py` 不再於 import time 固定 request-time 資料。
- 查驗 route 內 snapshot 只取得一次，且同時供查詢與成功寫入使用。
- 以 fake clock／mutation 證明第二次 request 會使用更新時間。
- 使用 GitHub CLI 查驗最新 PR HEAD、Python 3.10 runtime、三個 suites 與 read-only permissions。

## 8. 預計影響檔案

- `apps/game_broadcast_service/app.py`
- `apps/game_broadcast_service/request_time.py`（名稱可依附近風格微調）
- `apps/game_broadcast_service/tests/test_request_time.py`
- `apps/notify_cronjob_service/app.py`
- `docs/coordination/reports/TASK-005-CODEX.md`
- `docs/coordination/HANDOFF.yaml`
- 必要的 `PROJECT_STATE.md`／Work review 文件

不應修改 requirements、shared library、models、deployment config 或其他 services/functions。

## 9. 風險與假設

- 本任務假設現有 `+ timedelta(days=11)` 是應保留的產品行為，不重新解釋「未來十天」的文案。
- 改成 request-time snapshot 會讓長壽命 instance 使用正確日期，但不解決 Scheduler 重複投遞或多 instance 同時執行造成的競態。
- 離線測試可證明時間計算與 wiring，不代表 Cloud Run、Cloud Scheduler、資料庫或正式通知整合正確。
- 若 Codex 發現必須修改 shared library API、schema 或部署設定才能完成，應停止並交回 Work／Owner。

## 10. 建議 Git 與 PR

- branch：`codex/fix-broadcast-request-time`
- implementation commit／PR title：`fix(game-broadcast): compute announcement windows per request`
- TASK 編號放在 commit body/footer：`Refs TASK-005`
- 依 `COLLABORATION.md` 版本 1.3，原則上只建立一次 implementation commit 與一次 Codex 完工 commit；不得另建純交棒 commit。

## 11. Owner 決策需求

Owner 已於 2026-08-04：

1. 批准 TASK-005 的上述範圍並確認保留 11 天視窗規則。
2. 批准 DEC-004 定義的 PR 工作包。

授權包含 task branch、範圍內 commits、push、Draft PR、CI 查驗及同一 PR 的驗收文件更新；不包含 merge、部署、Secret、正式通知、production data 或不可逆操作。
