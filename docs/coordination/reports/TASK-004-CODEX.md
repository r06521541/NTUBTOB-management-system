# TASK-004 Codex 實作報告

更新時間：2026-08-04T22:27:41+08:00

## 任務狀態

- branch：`codex/fix-schedule-team-filter`
- base commit：`da7256e9a9698838b80e22f80d6ff593fcc9e56f`
- implementation commit：`11e96361db0158c47a82de1c1ebf87ca9a20bcec`
- Draft PR：待建立
- Python 3.10 CI：待驗證

## 實際修改

- 新增無 Flask、Functions Framework、資料庫、crawler 或通知 SDK 依賴的 `filter_games()` 純函式。
- `game_crawl()` 在 crawler response 經 `Game.from_dict()` 轉換後，改由 `filter_games()` 同時套用隊伍與包含邊界的日期條件。
- 保持隊名完全相等、輸入順序與既有錯誤處理；未改變 crawler、資料庫或通知流程。
- 新增 5 個離線 unit tests，涵蓋主客場、非本隊、範圍外、起訖邊界、空輸入與順序。
- Python 3.10 GitHub Actions workflow 新增 update game schedule suite，維持 `contents: read` 且不加入 Secret、部署、publish 或 dependency install。

## 修改檔案

- `.github/workflows/python-tests.yml`
- `functions/update_game_schedule/game_filter.py`
- `functions/update_game_schedule/main.py`
- `functions/update_game_schedule/tests/__init__.py`
- `functions/update_game_schedule/tests/test_game_filter.py`
- `docs/coordination/reports/TASK-004-CODEX.md`
- `docs/coordination/HANDOFF.yaml`（完成 CI 後更新）
- Work 既有的 TASK-004 決策、狀態與任務文件

## 驗證結果

使用 bundled Python 3.12.13 執行：

```text
python -m unittest discover -s functions/update_game_schedule/tests -v
Ran 5 tests — OK

python -m unittest discover -s apps/game_broadcast_service/tests -v
Ran 17 tests — OK

python -m unittest discover -s apps/notify_cronjob_service/tests -v
Ran 4 tests — OK
```

其他檢查：

- 以 `ast.parse(..., feature_version=(3, 10))` 驗證新增 Python 檔案的 Python 3.10 grammar：通過。
- helper imports 靜態檢查只包含標準函式庫 `datetime` 與 `typing`：通過。
- mutation 等價檢查證明只套用日期條件會錯誤保留非本隊賽事，與正確結果不同：通過。
- workflow 靜態安全檢查：包含新 suite、維持 read-only permissions、未加入 Secret／gcloud／deploy／publish：通過。
- `git diff --check` 與 staged diff check：通過。
- Black／isort：未執行；bundled Python 未安裝這兩個既有 formatter，未為此下載依賴。人工檢查新增檔案符合附近風格。

## 未執行與外部影響聲明

- 未呼叫 crawler、資料庫、LINE、Discord、weather 或其他外部 API。
- 未讀取 `.env.yaml` 或任何 Secret value。
- 未 build 或 deploy Cloud Function，未操作 GCP、GitHub settings、production data 或不可逆 migration。
- 未修改 requirements、shared library、database model/schema 或 deployment config。
- 本機未提供 Python 3.10 runtime；實際 Python 3.10 執行結果待 GitHub Actions 驗證。

## 尚存風險

- 測試只驗證純篩選行為，不證明 production crawler response、`Game.from_dict()`、資料庫資料或 Cloud Function 線上整合正確。
- 隊名仍採完全相等；資料來源若有 alias、空白或 Unicode 差異不在本任務處理範圍。
- 修正不清理既有資料庫中可能已混入的錯誤賽事。
- 工作樹另有使用者未追蹤資產 `apps/web_portal/static/images/logo_square.png`；本任務未讀取內容、未修改且不會納入 commit。
