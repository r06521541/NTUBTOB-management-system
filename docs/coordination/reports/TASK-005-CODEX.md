# TASK-005 Codex 實作報告

更新時間：2026-08-04T22:58:17+08:00

## 任務狀態

- 狀態：`ready_for_review`
- branch：`codex/fix-broadcast-request-time`
- base commit：`c70ce63d3b91fc0d224c86a1b8f3aba085f5979c`
- Work 規劃 commit：`2aedb188738433f6a21f52b5b8bf72fe715ab35e`
- implementation commit：`ba40ed35805fd6a9087340fbb907a5a0278e281a`
- Draft PR：[#29](https://github.com/r06521541/NTUBTOB-management-system/pull/29)
- Python 3.10 CI：run `30921643211`，job `92033479013`，成功

## 實際修改

- 新增純標準函式庫 `RequestTimeWindow` 與 `get_request_time_window()`，透過可注入 clock 每次取得一份 timezone-aware snapshot。
- 每次 invitation 與 cancellation request 各建立一次 snapshot；資料庫查詢下限及成功後寫入時間共用同一個 `now`，上限維持當日午夜加 11 天。
- `mark_games_as_invited()` 與 `mark_games_as_cancellation_announced()` 改由 caller 明確傳入寫入時間，不再讀 module global。
- 移除 game broadcast 的 import-time `now`、`today_begin`、`ten_days_later`。
- 移除 notify cron 未使用的 import-time 時間 globals 與相關 imports，未改變其 route 行為。
- 新增 7 個 standard-library-only tests，使用 fake clock 與 AST 靜態 wiring 檢查，不 import Flask、LINE SDK、shared library、資料庫或通知 client。

## 修改檔案

- `apps/game_broadcast_service/app.py`
- `apps/game_broadcast_service/request_time.py`
- `apps/game_broadcast_service/tests/test_request_time.py`
- `apps/notify_cronjob_service/app.py`
- `docs/coordination/reports/TASK-005-CODEX.md`
- `docs/coordination/HANDOFF.yaml`

## 執行命令與結果

使用 bundled CPython 3.12.13：

```text
python -m unittest discover -s apps/game_broadcast_service/tests -v
Ran 24 tests — OK

python -m unittest discover -s apps/notify_cronjob_service/tests -v
Ran 4 tests — OK

python -m unittest discover -s functions/update_game_schedule/tests -v
Ran 5 tests — OK
```

其他本機檢查：

- 以 `ast.parse(..., feature_version=(3, 10))` 檢查四個受影響 Python 檔案：通過。
- `git diff --check` 與 staged diff check：通過。
- fake clock 測試證明連續呼叫跨日會取得不同 snapshot；若固定為第一次值，測試會失敗。
- AST wiring tests 驗證兩個 routes 各呼叫一次 snapshot helper，查詢及 mark helper 共用 `request_time.now`，且兩服務沒有 import-time 時間 globals。
- Black／isort：未執行；bundled Python 未安裝 repository 指定版本，未為此下載依賴或修改環境。

GitHub Actions 使用 CPython 3.10.20：

- game broadcast：24/24，`OK`
- notify cron：4/4，`OK`
- update game schedule：5/5，`OK`
- job conclusion：`SUCCESS`
- token permissions：`contents: read`、`metadata: read`

## 未執行與外部影響聲明

- 未 import 或啟動完整 Flask applications 作線上整合測試；CI 亦未安裝 application dependencies。
- 未呼叫 LINE、Discord、資料庫、crawler、weather、GCP 或其他外部服務。
- 未讀取 `.env.yaml` 或 Secret value。
- 未 build、deploy、修改 Cloud Scheduler／Cloud Run／Cloud Build／IAM／Secret／環境變數。
- 未修改 requirements、shared library、database model/schema 或 production data，沒有 migration。

## 假設、風險與阻礙

- 依 Owner 決策保留 `today_begin + timedelta(days=11)`，未重新解釋產品視窗。
- 離線 helper 與 wiring tests 不證明 Cloud Run、Scheduler、資料庫或正式通知整合正確。
- 本修正不處理重複投遞、多 instance 競態、idempotency 或通知去重。
- `datetime.replace()` 保留既有 Asia/Taipei timezone；本任務未新增其他 timezone 規則。
- 工作樹另有使用者未追蹤資產 `apps/web_portal/static/images/logo_square.png`；未修改且未納入 commit。
- 無 blocking issue；目前不需要 Owner 額外決策，下一步為 Work 獨立驗收。

## 未提交修改

Codex 任務檔案會隨本報告與 HANDOFF 一次提交。除使用者未追蹤圖片外，沒有其他未提交修改。
