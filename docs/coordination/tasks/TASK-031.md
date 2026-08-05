# TASK-031：Resolve gcloud Executable Safely on Windows

狀態：`ready_for_codex`
優先級：P1 deployment blocker
規劃者：Work
執行者：Codex
Base commit：`c3611e5fecddf8856f8e58835bb3065f61c704b6`

## 1. 任務目標

修正 `tools/deploy_web_portal.py` 在 Windows 上雖由 preflight 找到 `gcloud.cmd`，實際 subprocess 卻硬編碼執行 `gcloud` 而拋出 `FileNotFoundError` 的問題，使 wrapper 能安全使用已解析的 executable，同時保持 Linux／macOS 的 `gcloud` 行為與既有 fail-closed deployment contract。

## 2. 實際失敗證據

- TASK-030 exact commit：`6765448ac64950cfe35008e637bc2c529954e106`
- `where.exe gcloud`：同時找到 Cloud SDK 的 `gcloud` 與 `gcloud.cmd`。
- PowerShell直接執行 `gcloud` 的唯讀查詢成功。
- Wrapper在 `command_output(..., ["gcloud", "run", ...])` 啟動階段拋出 Windows `FileNotFoundError`。
- 失敗前沒有取得Cloud Build ID；唯讀確認沒有新build／revision，traffic仍為 `web-portal-00027-fwf=100%`，temporary env已清除。

## 3. 工作範圍

- 建立一個集中、可測試的 executable resolution方式，回傳可供 `subprocess.run(shell=False)` 安全使用的 command prefix或exact executable。
- Windows應使用實際可執行的 Cloud SDK入口（包含必要的 `.cmd` handling）；不得透過任意shell string、字串拼接或 `shell=True` 擴張command injection邊界。
- 所有 Web Portal wrapper 的 gcloud calls必須使用同一個已解析結果，不得只有第一個command修正。
- 檢查 `tools/deploy_scheduled_service.py` 是否有相同缺口；若共用helper可在小範圍內安全修正兩個wrapper並補測試。不得改變其CLI或deployment語意。
- 新增可離線 regression tests，模擬Windows只有 `gcloud.cmd` 可解析時，實際 runner收到可執行的argv；同時涵蓋POSIX `gcloud`。
- 補測 executable缺失或解析結果不可執行時，在cloud mutation前fail closed。
- 在 TASK-031 report記錄 TASK-030 deployment attempt未造成production mutation。

## 4. 非目標與禁止事項

- 不執行任何wrapper `--execute`、gcloud、HTTP、Cloud Build或Cloud Run命令。
- 不部署、不rollback、不呼叫LINE、不連production DB。
- 不讀取、複製或顯示 `envs/**/.env.yaml` 或Secret payload。
- 不修改application routes、LINE Login邏輯、schema、IAM、Secret、Scheduler或deployment config。
- 不以 `shell=True`、臨時系統PATH修改、shim executable或手動Cloud Build繞過問題。
- 不重設或清理本機diverged `main`。

## 5. 驗收條件

- Windows `gcloud.cmd` resolution有明確回歸測試，且所有gcloud subprocess argv使用解析結果。
- POSIX `gcloud` resolution保持相容。
- 不使用shell command string或 `shell=True`。
- Web Portal與scheduled-service wrapper完整tests通過。
- Web Portal application tests保持通過。
- Python 3.10 CI成功。
- `git diff --check`、compile check與wrapper dry-run通過；dry-run不得執行任何外部命令。
- Codex report、Work review、PROJECT_STATE與HANDOFF依協作流程更新。

## 6. 驗證命令

```powershell
python -m unittest discover -s tools/tests -v
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q tools apps/web_portal
python tools/deploy_web_portal.py
git diff --check
git status --short
```

測試必須mock executable lookup與runner；不得為驗證本任務呼叫真實 `gcloud`。

## 7. PR 工作包授權

Owner 已批准 TASK-031 及完整 PR 工作包：允許建立／切換task branch、修改上述工具／測試／文件、建立描述性commit、push、建立或更新Draft PR、唯讀監看CI，並依CI與Work驗收結果更新同一PR。仍不包含merge、production deployment、wrapper `--execute`、Secret／IAM／LINE Console／DB／schema／data修改或通知。

TASK-031 merge後，Work須以新的main exact commit更新TASK-030；舊的 `6765448...` 不再作下一次deployment source。
