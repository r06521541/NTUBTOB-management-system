# TASK-002：建立 Python 3.10 GitHub Actions CI

狀態：`completed`
優先級：P2
建立者：Work
`base_commit`：`6d2dad083b1f270b5f89b2c742338121d59b3d15`

## 1. 任務目標

建立最小、唯讀且不含部署行為的 GitHub Actions workflow，在 pull request、main branch push 或手動觸發時，以 Python 3.10 執行 `game_broadcast_service` 完整 unittest suite，補足目前只有 Python 3.12 本機證據的版本驗證缺口。

## 2. 背景與現況

- 專案以 Python 3.10 為基準，Cloud Run Dockerfile 與 Cloud Functions runtime 也使用 Python 3.10。
- TASK-001 已新增 4 個部署契約測試；目前完整 suite 共 17 tests。
- 本機可用 runtime 為 Python 3.12.13。Windows launcher 雖保留 Python 3.10 registration，但 executable 已無法啟動。
- Repository 目前沒有 `.github/` 或 CI workflow。
- TASK-001 已由 Owner 接受並提交於 `6d2dad0`；目前 working tree 乾淨。

GitHub 官方建議使用 `setup-python` 明確指定版本，以避免 runner 預設 Python 漂移；安全指南建議 workflow token 採最小權限，並將 actions pin 到完整 commit SHA。

官方參考：

- `https://docs.github.com/en/actions/tutorials/build-and-test-code/python`
- `https://docs.github.com/en/actions/reference/security/secure-use`
- `https://github.com/actions/checkout`
- `https://github.com/actions/setup-python`

## 3. 工作範圍

- 新增一個 workflow，例如 `.github/workflows/python-tests.yml`。
- Workflow 名稱與 job 名稱需能辨識為 Python 3.10 tests。
- 觸發條件：
  - `pull_request`
  - `push` 到 `main`
  - `workflow_dispatch`
- 明確設定：
  - `permissions: contents: read`
  - `runs-on: ubuntu-latest`
  - 合理的 `timeout-minutes`，建議不超過 10 分鐘
  - Python version 精確指定為 `3.10`
- Steps 至少包含：
  1. checkout repository。
  2. 以官方 `actions/setup-python` 設定 Python 3.10。
  3. 顯示/確認實際 Python version。
  4. 執行 `python -m unittest discover -s apps/game_broadcast_service/tests -v`。
- `actions/checkout` 與 `actions/setup-python` 必須使用官方 repository 的 release commit，pin 到完整 40-character SHA，並以註解標示對應 release tag。
- Codex 必須從官方 action repository/release 驗證 tag 與 SHA，並在 report 記錄來源；不得從第三方文章複製 SHA。
- 目前 17 tests 不需要安裝 application dependencies；不要加入 `pip install -r requirements.txt`、cache、artifact upload 或其他非必要步驟。
- 完成實作後建立 `docs/coordination/reports/TASK-002-CODEX.md`，並依流程更新 `HANDOFF.yaml`。

## 4. 明確非目標

- 不建立 deployment、build image、release、package publish 或 GCP workflow。
- 不加入 Cloud Run、Cloud Build、Cloud Functions、Secret Manager、LINE、Discord、crawler、weather 或 DB 操作。
- 不使用 GitHub Secrets、environment secrets、OIDC 或 cloud credentials。
- 不新增 lint、format、coverage、dependency cache、matrix 或多作業系統測試。
- 不修改 application code、deployment config、Makefile、requirements 或既有 tests，除非 workflow 靜態驗證揭露任務本身無法成立；此時先回報，不擴張修正。
- 不啟用或修改 GitHub repository/organization Actions settings 或 branch protection。
- 不 commit、push、開 PR 或手動觸發線上 workflow。

## 5. 驗收條件

- [ ] 只有一個新的 Python test workflow，範圍小且名稱清楚。
- [ ] Workflow 由 `pull_request`、main branch `push` 與 `workflow_dispatch` 觸發，不使用 `pull_request_target`。
- [ ] `GITHUB_TOKEN` 權限明確限制為 `contents: read`，沒有任何 write permission。
- [ ] 使用 `ubuntu-latest` 並精確指定 Python `3.10`。
- [ ] 官方 actions 均 pin 到完整 40-character commit SHA，註解保留 release tag，report 記錄官方來源。
- [ ] Job 有不超過 10 分鐘的 timeout。
- [ ] Workflow 顯示 Python version 並執行完整 17-test unittest command。
- [ ] Workflow 不安裝 application dependencies、不使用 secrets、不含 deploy/publish/cloud 命令。
- [ ] 現有 17 tests 在可用本機 runtime 仍通過。
- [ ] Workflow YAML 可被可用的本機 parser 或靜態工具解析；若環境沒有 parser/actionlint，Codex 必須明說，不能宣稱 GitHub 已接受語法。
- [ ] `git diff --check` 通過，實際 diff 只包含 workflow、Codex report 與 handoff 更新。
- [ ] Codex report 符合 `COLLABORATION.md` 第八節最低要求。

## 6. 必要測試

至少執行：

```sh
python -m unittest discover -s apps/game_broadcast_service/tests -v
git diff --check
git status --short
```

另外必須以唯讀方式檢查 workflow：

- YAML 語法可解析，或清楚記錄無 parser 的限制。
- action references 為完整 SHA。
- 沒有 `pull_request_target`、`secrets`、write permission、`gcloud`、deploy 或 publish command。

Codex 不得自行 push，因此第一次真正的 GitHub Actions run 不可能在本任務實作階段完成。Codex report 與 Work review 必須把「repository 靜態驗證」與「Owner push 後的線上 run」分開描述。

## 7. 安全限制

- Workflow 僅允許讀 repository 與執行離線 unittest。
- 不授予 `contents: write`、`actions: write`、`id-token: write`、`packages: write` 或其他 write permission。
- 不引用 `${{ secrets.* }}`、GitHub environments 或 cloud credentials。
- 不允許 `pull_request_target`，避免以 base repository 權限執行不受信任 PR code。
- 不下載或執行非官方 action；官方 actions 仍需 pin 到完整 SHA。
- 不讀取真實 `.env.yaml`，不連線 production/staging 服務，不發送通知。
- 不部署、不修改 GCP/GitHub 設定、不 commit、不 push。

## 8. 相關檔案與模組

- `AGENTS.md`
- `docs/coordination/COLLABORATION.md`
- `docs/coordination/HANDOFF.yaml`
- `docs/coordination/PROJECT_STATE.md`
- `docs/coordination/DECISIONS.md`
- `docs/coordination/tasks/TASK-002.md`
- `.github/workflows/python-tests.yml`（預計新增）
- `apps/game_broadcast_service/tests/test_game_reminder.py`
- `apps/game_broadcast_service/tests/test_deployment_contract.py`

## 9. 已知風險

- GitHub Actions 或 organization policy 可能被停用、限制官方 actions，或要求特定 SHA pinning policy；repository 內容無法證實遠端設定。
- GitHub-hosted runner 與 action runtime 會更新；完整 SHA 提高不可變性，但未來仍需主動升版。
- 本機靜態解析不能取代 GitHub 接收 workflow 後的實際 run。
- 若 default branch 不是 `main`，push trigger 需要另案調整；本 repository 有本機 `main` branch，但未查遠端 default branch。
- CI 通過只證明 17 個隔離測試，不代表 Cloud Build、Cloud Run、Secret、DB、LINE 或外部 API 整合正確。

## 10. 需要 Owner 決策的事項

- Owner 已批准建立 TASK-002 與最小 Python 3.10 CI。
- Owner 尚未批准 commit、push、啟用 GitHub Actions settings 或 branch protection。
- Work 驗收 repository diff 後，Owner 需決定是否 commit/push；第一次線上 run 結果應在 push 後另行確認，不能預先宣稱通過。

## 11. Codex 交付與交棒

Codex 完成後必須：

1. 建立 `docs/coordination/reports/TASK-002-CODEX.md`。
2. 記錄 workflow、action tag/SHA 官方來源、實際命令、測試結果、未執行的線上 CI、風險與 working tree。
3. 更新 `docs/coordination/HANDOFF.yaml`：
   - `status: ready_for_review`
   - `next_actor: work`
   - `head_commit` 填目前 HEAD；若沒有新 commit，note 明確說明成果為未提交 diff。
4. 不自行把任務設為 completed，不 commit、不 push、不觸發 workflow。
