# TASK-031 Codex 實作報告

更新時間：2026-08-06（Asia/Taipei）

## 任務狀態

- 狀態：`ready_for_review`
- branch：`codex/fix-windows-gcloud-resolution`
- base commit：`c3611e5fecddf8856f8e58835bb3065f61c704b6`
- task planning commit：`26ad86c`
- implementation commit：`f21d54f`

## 完成內容

- `tools/deploy_web_portal.py` 與 `tools/deploy_scheduled_service.py` 現在都在唯一的 subprocess 邊界使用 `shutil.which` 解析 exact executable。
- Windows 可把 `gcloud` 解析成 `gcloud.cmd` 後以 argument list 執行；沒有使用 command string 或 `shell=True`。
- POSIX 仍可解析 `/usr/bin/gcloud` 類型的 executable path。
- executable 不存在或 command 為空時 fail closed，不會嘗試執行。
- 所有既有 gcloud 路徑（build、describe、驗證、traffic 與 rollback）都經過同一個 runner 邊界，因此沒有只修正單一 command。
- 兩個 wrapper 都新增 Windows `.cmd` 真實離線執行、mock exact argv、POSIX path 與 missing executable 測試。

## 驗證結果

使用工作區 bundled Python 執行：

```text
python -m unittest discover -s tools/tests -v
Ran 34 tests — OK

python -m unittest discover -s apps/web_portal/tests -v
Ran 55 tests — OK (skipped=2)

python -m compileall -q tools apps/web_portal
passed

ast.parse(..., feature_version=(3, 10))
passed for both wrappers and their tests

python tools/deploy_web_portal.py
Preflight passed; no cloud or HTTP commands were run.

python tools/deploy_scheduled_service.py game-broadcast-service
Preflight passed; no cloud commands were run.

git diff --check
passed
```

兩項 Web Portal skip 是 Windows 缺少 Unix `make`／`sh` 的既有 Make contract；本任務新增的 Windows executable tests 沒有 skip。

驗證過程曾以錯誤的 underscore service 名稱執行 scheduled wrapper，CLI 依設計拒絕，修正為 `game-broadcast-service` 後 dry-run 通過；兩次都未進入 `--execute`。

## 安全邊界

- 未執行 wrapper `--execute`。
- 未呼叫 gcloud、HTTP、Cloud Build、Cloud Run 或 production。
- 未讀取 env YAML、Secret、DB 或 LINE 資料。
- 未修改 schema、IAM、Secret、Scheduler 或 deployment config。

## 尚未驗證與風險

- 真實 `gcloud.cmd` 的完整 production command 尚未執行；本機使用臨時 `.cmd` 檔驗證 Windows `subprocess(shell=False)` 啟動契約。
- Hosted Python 3.10 CI 需由 Draft PR 實跑確認。
- TASK-030 的 exact deployment source 必須在 TASK-031 merge 後由 Work 重新鎖定；不得沿用舊 commit。
