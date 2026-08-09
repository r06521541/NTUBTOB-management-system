# TASK-019 Codex Implementation Report

日期：2026-08-05  
狀態：`ready_for_review`  
PR：[Draft PR #33](https://github.com/r06521541/NTUBTOB-management-system/pull/33)

## Git 範圍

- Task base（HANDOFF）：`b14dcad3d1261772c8dc00898ba1caca114ce941`
- Codex 開始實作時 HEAD：`d8ca20f`（包含 Owner 已批准的 TASK-016～019 coordination／deployment 紀錄）
- 初始實作 commit：`0c9cc77 feat(deployment): make scheduled service rollouts commit-addressable`
- Work 安全補正 commit：`294970f fix(deployment): verify new revisions before shifting traffic`
- Production-shape 補正 commit：`468801b fix(deployment): validate pinned revisions by readiness conditions`
- Branch：`codex/immutable-scheduled-service-deployments`
- PR base／head：`main`／上述 branch

## 完成內容

- 兩個 scheduled services 的 Cloud Build build、push、deploy image reference 改用 `_IMAGE_TAG`，不再使用固定 `:tag1`。
- Legacy Make targets 將完整 `git rev-parse HEAD` 傳入 `_IMAGE_TAG`，並擴大暫存 env 的 Secret key 排除範圍。
- 新增 Python 3.10-compatible、Windows／Unix-like 共用 deployment wrapper：
  - 預設只做 local repository preflight，不執行 `gcloud`。
  - `--execute` 必須提供完整 approved commit 與屬於 target service 的 exact rollback revision。
  - 檢查 clean tree、HEAD、target source、env source、Cloud Build config 與暫存 env 衝突。
  - 重建／複製 shared sdist、過濾 runtime Secret keys，以 `finally` 清理暫存 `.env.yaml`。
  - 用批准 SHA 作 image tag，要求 Cloud Build `SUCCESS` 與 build ID。
  - 查驗 distinct／ready revision 及 image digest，明確指派並驗證 100% traffic。
  - rollout 失敗時嘗試切回 exact approved rollback revision。
- 新增 fake runner 離線測試、deployment contracts、CI、README 與 runbook 更新。
- Web Portal Cloud Build 未修改，仍維持禁止部署邊界。

## 驗證結果

本機可用 Python 3.9（不依賴 Flask 的離線相容性檢查）：

- Wrapper tests：7/7 通過。
- 兩個 deployment contract suites：10/10 通過。
- `compileall`：通過。
- 完整服務測試因該 interpreter 沒有 Flask 而各有 3 個環境型 import errors；未宣稱本機完整通過。
- 乾淨 commit 後，兩個服務未帶 `--execute` 的 preflight 均通過，且沒有 cloud commands。
- `git diff --check`：通過。

GitHub Actions run `30980267182`／job `92222996040`：

- CPython `3.10.20`。
- Game broadcast：28/28；Notify cron：9/9；Wrapper：7/7；Update schedule：5/5。
- 結果：`SUCCESS`。

## 安全邊界

- 未執行 wrapper `--execute` path、`gcloud builds submit`、deployment、traffic mutation 或 production 查詢。
- 未讀取／顯示 Secret value，未連 production DB，未發送 LINE／Discord 通知。
- 未修改 shared library source、schema、Secret、IAM、Scheduler、Web Portal deployment config 或其他服務。
- 未 merge PR。

## 未驗證與殘餘風險

- Execute path 只以 fake runner 驗證；尚無真實 Cloud Build／Cloud Run integration evidence，首次 production 使用仍須 Owner 核准並由 Work 依 runbook 監督。
- Rollout 失敗會嘗試 rollback，但 rollback 仍可能因外部 IAM／平台錯誤失敗並明確報錯。
- 本機 Python 3.10 安裝已失效且沒有 `python` alias；Python 3.10 證據來自 GitHub hosted runner。
- PR 包含自 `b14dcad` 後已由 Owner 接受但尚未 push 的 coordination／deployment closeout commits；Work 應查驗 PR 全部 commit 範圍。

## Work review 補正

Work 於 commit `7126ee4` 提出 `changes_requested` 後，已完成：

- Cloud Build 前先捕捉 `latestCreatedRevisionName` baseline；build 後 revision 必須不同，避免 stale latest revision 被誤認為本次部署。
- 以批准 SHA tag 查詢 Artifact Registry digest，並要求與 revision `status.imageDigest` 精確一致後才允許顯式導流。
- 敏感 env key 即使帶有前置空白或 tab 仍會被排除；fixture values 不出現在 temporary env、命令或錯誤文字。
- 移除 clean checkout 必須預先存在 ignored `shared_lib/dist` 的錯誤前置條件；fake build 會建立 dist 與 artifact。
- 新增 deploy no-op、digest mismatch、traffic command failure、traffic verification failure測試；失敗時只使用 exact approved rollback revision，且一律清理 temporary env。

補正後本機 wrapper tests：11/11 通過；deployment contracts：10/10 通過；compile 與 `git diff --check` 通過。

補正後 GitHub Actions：

- Run：`30981449322`
- Job：`92226558256`
- CPython 3.10 suite：`SUCCESS`
- 未執行 wrapper `--execute`、gcloud 或任何 production 操作。

### 第二輪 production-shape 補正

Work 以 TASK-017／018 的實際 Cloud Run metadata 指出兩項差異後，已完成：

- Pinned traffic 情境下，切流量前不再要求 service `latestReadyRevisionName` 已指向新 revision；改查新 revision 自身的 `Ready=True` condition。
- 完成 traffic assignment 後，才同時驗證 service `latestReadyRevisionName` 與 100% traffic 指向新 revision。
- Artifact Registry 回傳的 bare `sha256:...` 與 Cloud Run 回傳的完整 `registry/image@sha256:...` 均正規化為嚴格 64 位十六進位 digest，再做精確比較。
- Fake runner 模擬 pre-traffic latest ready 仍是 baseline、revision 自身 Ready，以及完整 image reference digest；full-reference match 成功、mismatch 停止並 rollback。

第二輪補正後 GitHub Actions run `30982277507`／job `92229079528` 使用 Python 3.10 並成功通過。全程未執行 wrapper execute path 或任何雲端操作。

## 變更檔案

- `.github/workflows/python-tests.yml`
- `README.md`
- `apps/game_broadcast_service/cloudbuild.yaml`
- `apps/game_broadcast_service/tests/test_deployment_contract.py`
- `apps/notify_cronjob_service/cloudbuild.yaml`
- `apps/notify_cronjob_service/tests/test_deployment_contract.py`
- `docs/operations/DEPLOYMENT_RUNBOOK.md`
- `makes/deploy_apps.mk`
- `tools/deploy_scheduled_service.py`
- `tools/tests/test_deploy_scheduled_service.py`
