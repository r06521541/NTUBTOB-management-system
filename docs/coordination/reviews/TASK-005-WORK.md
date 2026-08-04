# TASK-005 Work 驗收報告

驗收時間：2026-08-04T23:02:06+08:00
驗收者：Work
驗收結論：`accepted`
下一位角色：`owner`

## 1. 驗收基準

- branch：`codex/fix-broadcast-request-time`
- code base：`c70ce63d3b91fc0d224c86a1b8f3aba085f5979c`
- Work planning：`2aedb188738433f6a21f52b5b8bf72fe715ab35e`
- implementation：`ba40ed35805fd6a9087340fbb907a5a0278e281a`
- Codex completion：`3969833d24b739bdd819baf11dcdeec7e9f8954a`
- Draft PR：[#29](https://github.com/r06521541/NTUBTOB-management-system/pull/29)
- Work 已查驗實際 diff、commits、程式碼、tests、PR 與最新 CI log，沒有只依賴 Codex report。
- 工作樹唯一額外狀態是 Owner 的未追蹤隊徽；TASK-005 未修改或納入該資產。

## 2. 實際修改查驗

- 新增 standard-library-only `RequestTimeWindow` 與 `get_request_time_window()`，clock 可注入且每次呼叫取得新 snapshot。
- Invitation 與 cancellation routes 各在 request 內呼叫一次 helper。
- 同一 request 的查詢下限與成功寫入時間共用 `request_time.now`，查詢上限維持當日午夜加 11 天。
- 兩個 mark helpers 改由 caller 明確傳入 timestamp，不再讀 module global。
- Game broadcast 不再於 import time 固定 `now`、`today_begin`、`ten_days_later`。
- Notify cron 只移除未使用的 import-time 時間 globals 與 imports，route 行為未變。
- 新增 7 個離線 tests；沒有修改 requirements、shared library、schema、migration、部署或 Secret 設定。

## 3. 驗收條件結果

| 驗收條件 | 結果 | 證據 |
| --- | --- | --- |
| 每次呼叫取得新 clock value | 通過 | Fake clock 跨日連續呼叫得到 8/4 與 8/5 snapshots。 |
| Asia/Taipei 當日午夜與 11 天上限 | 通過 | Helper test 驗證 timezone-aware midnight 與 `+ timedelta(days=11)`。 |
| Invitation 每 request 只取一次 snapshot | 通過 | AST wiring test 及 Work 實際 diff 查驗。 |
| Invitation 查詢與寫入共用 now | 通過 | 查詢及 mark helper 均使用 `request_time.now`。 |
| Cancellation 每 request 只取一次 snapshot | 通過 | AST wiring test 及 Work 實際 diff 查驗。 |
| Cancellation 查詢與寫入共用 now | 通過 | 查詢及 mark helper 均使用 `request_time.now`。 |
| 移除兩服務 import-time 時間 globals | 通過 | AST tests 與實際 source 查驗。 |
| 原錯誤型 mutation 可辨識 | 通過 | Work 模擬 cache 第一個 snapshot；第二次跨日 request 與正確結果不同。 |
| 本機三套 tests | 通過 | game broadcast 24/24、notify cron 4/4、schedule 5/5。 |
| Python 3.10 CI | 通過 | 最新 HEAD run `30921789436` 使用 CPython 3.10.20，三套 tests 全數通過。 |
| Workflow 安全邊界 | 通過 | `Contents: read`；沒有新增 workflow、Secret、deploy、publish 或 dependency install。 |
| Python 3.10 grammar／diff | 通過 | 四個受影響 Python 檔案 parse 成功；`git diff --check` 無錯。 |
| Commit 精簡規則 | 通過 | 一個 implementation commit 加一個 Codex completion commit，沒有純交棒 commit。 |

## 4. Work 獨立驗證

```text
bundled Python 3.12.13
game_broadcast_service: Ran 24 tests — OK
notify_cronjob_service: Ran 4 tests — OK
update_game_schedule: Ran 5 tests — OK
Python 3.10 grammar parse: OK
cached/import-time mutation: detected
git diff --check: OK
```

GitHub Actions 最新證據：run `30921789436`、job `92033978634`、head `3969833d24b739bdd819baf11dcdeec7e9f8954a`、CPython `3.10.20`、結論 `SUCCESS`。

## 5. 回歸風險與限制

- 離線 helper 與 AST wiring tests 不代表 Cloud Run、Scheduler、資料庫或正式通知整合正確。
- 本任務未處理 Scheduler 重複投遞、多 instance 競態、idempotency 或通知去重。
- 11 天上限依 Owner 決策維持，不重新定義邀請提前範圍。
- 未執行 Black／isort、Cloud Build、deploy、staging smoke test 或任何 GCP 操作。

## 6. Blocking 問題

無。

## 7. 驗收結論

`accepted`

TASK-005 已消除 game broadcast 使用 container 啟動時間作為後續 request 時間的風險，並保留既有 11 天產品規則。建議 Work review push 後等待最終 CI，再由 Owner 決定是否將 PR #29 標記 ready 並 merge。

此結論不批准部署、Secret 操作、正式 LINE／Discord 通知、production data 操作或不可逆變更。
