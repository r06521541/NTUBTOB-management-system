# TASK-002 Codex 實作報告

## 任務狀態

- 狀態：`ready_for_review`
- base commit：`6d2dad083b1f270b5f89b2c742338121d59b3d15`
- head commit：`6d2dad083b1f270b5f89b2c742338121d59b3d15`
- branch：`fix/weather-api-secret`
- 成果形式：未提交 diff；未建立 commit、push、PR，也未觸發線上 workflow。

## 實際修改內容

- 新增唯一一個 GitHub Actions workflow，以 Python 3.10 執行 `game_broadcast_service` 完整 unittest suite。
- Workflow 觸發條件為 `pull_request`、push 到 `main` 與 `workflow_dispatch`，未使用 `pull_request_target`。
- Workflow token 權限明確限制為 `contents: read`。
- Job 使用 `ubuntu-latest`，timeout 為 10 分鐘。
- Workflow 顯示實際 Python version，再執行現有 17-test command。
- 沒有 dependency install、cache、artifact、Secrets、environment、cloud credential、deploy 或 publish 步驟。
- 兩個官方 actions 均 pin 到完整 40-character release commit SHA，並保留 release tag 註解。

## 官方 action 來源

- `actions/checkout` v7.0.1：
  - release：`https://github.com/actions/checkout/releases/tag/v7.0.1`
  - 官方 commit：`https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1`
  - SHA：`3d3c42e5aac5ba805825da76410c181273ba90b1`
- `actions/setup-python` v7.0.0：
  - release：`https://github.com/actions/setup-python/releases/tag/v7.0.0`
  - 官方 commit：`https://github.com/actions/setup-python/commit/5fda3b95a4ea91299a34e894583c3862153e4b97`
  - SHA：`5fda3b95a4ea91299a34e894583c3862153e4b97`

上述 tag 與完整 SHA 均直接由 GitHub 官方 `actions/*` repository 的 release/commit 頁面確認，未使用第三方文章。

## 修改檔案

- `.github/workflows/python-tests.yml`：新增 Python 3.10 read-only unittest workflow。
- `docs/coordination/reports/TASK-002-CODEX.md`：本報告。
- `docs/coordination/HANDOFF.yaml`：交棒給 Work review。

開始任務時已存在的 Work 變更為 `docs/coordination/DECISIONS.md`、`PROJECT_STATE.md`、`HANDOFF.yaml` 與未追蹤的 TASK-002 規格；本次保留這些內容，只更新 handoff 的交棒欄位與 note。

## 執行過的命令與結果

1. Repository 接手檢查：

   ```text
   git branch --show-current
   git rev-parse HEAD
   git status --short --branch
   ```

   結果：branch 為 `fix/weather-api-secret`；HEAD 與 task `base_commit` 均為 `6d2dad083b1f270b5f89b2c742338121d59b3d15`。既存 Work 文件變更與 TASK-002 交接內容一致。

2. 本機 unittest：

   ```text
   C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s apps/game_broadcast_service/tests -v
   ```

   結果：Python 3.12.13；17 tests passed。

3. Workflow 靜態安全契約檢查：

   - 確認只有一個 `.github` workflow。
   - 確認兩個 `uses:` reference 都是官方 action 與完整 40-character SHA。
   - 確認三種觸發條件、`contents: read`、`ubuntu-latest`、Python `3.10`、10 分鐘 timeout、version 與 unittest commands。
   - 確認沒有 `pull_request_target`、write permission、`${{ secrets.* }}`、GitHub environment、`gcloud`、deploy、publish、`pip install` 或 artifact upload。

   結果：全部通過。

4. Diff 檢查：

   ```text
   git diff --check
   git status --short --branch
   ```

   結果：沒有 whitespace error；Windows Git 僅顯示既有 LF→CRLF warning。

## 未執行或無法執行的測試

- Bundled Python 沒有 PyYAML，bundled Node modules 也沒有 `yaml`、`js-yaml` 或 `actionlint`；因此無法以本機 YAML parser/actionlint 驗證，不能宣稱 GitHub 已接受 workflow 語法。
- 沒有 commit 或 push，因此沒有觸發 GitHub Actions，也沒有 Python 3.10 hosted runner 的實際結果。
- 依 task 非目標，沒有安裝 dependencies、執行 application build、Docker build、部署或外部整合測試。

## 測試隔離與安全

- 本機只執行既有離線 unittest 與 workflow 文字靜態檢查。
- 沒有讀取 `.env.yaml`、GitHub Secrets 或任何真實 secret。
- 沒有連線 DB、GCP、LINE、Discord、crawler 或 weather API。
- 沒有 commit、push、PR、GitHub 設定變更或 production deployment。

## 假設、風險與阻礙

- 假設 repository remote default branch 為 `main`；task 明確指定 push trigger 使用 `main`，但本次未查詢遠端設定。
- 靜態檢查不能取代 GitHub Actions parser 與 hosted runner 的第一次線上 run。
- 完整 SHA 提供不可變 reference，但 action release 日後仍需由後續維護任務升版。
- CI 通過只能證明目前 17 個隔離 tests，不代表 Cloud Build、Cloud Run、Secret、DB、LINE 或外部 API 整合正確。
- 無 blocking implementation issue；TASK-002 可交由 Work review。

## 變更影響聲明

- 未修改 application code、既有 tests、Makefile、requirements、deployment config、環境變數或 database schema。
- 不涉及 migration、Secret Manager 或正式部署設定。
- Owner 後續仍需決定是否 commit/push；只有 push 後才能取得 GitHub Actions 與 Python 3.10 runtime 的實際證據。
