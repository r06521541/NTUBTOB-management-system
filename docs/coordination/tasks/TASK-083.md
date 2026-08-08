# TASK-083：修正 regional Cloud Build deployment resume

## 目標

修正 `tools.deploy_scheduled_service` 在 regional Cloud Build 完成後解析 submit output 失敗，以及 `--resume-verify-only` 查詢 build 時漏帶 region 的缺陷，使既有成功 build 能安全接續 candidate 驗證與 promotion。

## 背景與已確認事實

- TASK-082 部署 notify cron 時，regional Cloud Build `f4c6e0a4-f1b6-45f7-8478-85dc8042517c` 實際為 SUCCESS，candidate revision 也已建立，但 wrapper 回報 `Invalid JSON returned for Cloud Build`。
- `resume_verify_only()` 目前執行 `gcloud builds describe` 時沒有 `--region asia-east1`，因此無法查到 regional build。
- `gcloud builds submit` 目前沒有壓制 streamed logs，stdout 可能不是單一 JSON document。
- 工具目前 fail closed，沒有因上述錯誤自動改變 traffic；本任務不得降低此邊界。

## 工作範圍

1. Scheduled-service build submit 明確抑制 streamed build logs，使 machine-readable output 可安全解析。
2. 所有 scheduled-service `gcloud builds describe` 查詢必須帶入精確 `--region asia-east1`。
3. 新增 regression tests，至少證明：
   - submit command 包含 suppress-logs 與 region；
   - resume describe command 包含精確 region；
   - SUCCESS build 可接續既有 candidate 驗證與 promotion；
   - failed、working、invalid JSON、wrong substitutions 與 ambiguous traffic 仍 fail closed，且不 promotion。
4. 若現有 parser 仍需最小強化，只接受單一明確 build object；不得從任意混雜文字猜取 JSON。
5. 更新 Codex report 與 handoff。

## 非目標

- 不執行 gcloud、Cloud Build、部署、traffic mutation 或 production metadata 查詢。
- 不修改 Cloud Build YAML、服務 runtime、環境變數、Secret、IAM、Scheduler 或資料庫。
- 不擴張到 Web Portal deployment wrapper，除非直接共用且測試證明必要；預設不改。
- 不重寫 deployment framework。

## 驗收條件

- regional build submit output 不再因 streamed logs 汙染而觸發 JSON parsing failure。
- resume 對 regional build 使用精確 region，且保留 full SHA、service、candidate、digest、latest-created、exact rollback baseline 與 100% traffic 驗證。
- 任何未知／混合狀態仍在 traffic mutation 前停止。
- Python 3.10 相容。
- 受影響 deployment tests、compileall、Black formatter API content check 與 `git diff --check` 通過。

## 建議驗證命令

```powershell
C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest tools.tests.test_deploy_scheduled_service -v
C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m compileall -q tools\deploy_scheduled_service.py tools\tests\test_deploy_scheduled_service.py
git diff --check
git status --short
```

Bundled Windows Python 不執行 Black CLI；使用 repository 指定 Black 24.4.2 formatter API 比對本次 Python 檔案，最終以 hosted CI 為準。

## 安全限制

- 僅 repository／local 修改與離線測試。
- 不讀取 `envs/**/.env.yaml` 或任何 Secret 值。
- 不部署、不 build、不查詢或修改 production。
- 不 commit、push、建立 PR，直到 Codex 完成實作與 Work 驗收流程需要；既有 standing Git authorization 仍適用。

## 相關檔案

- `tools/deploy_scheduled_service.py`
- `tools/tests/test_deploy_scheduled_service.py`
- `docs/operations/deployments/PHASE_C_ACTIVATION_AE6A345.md`
- `docs/coordination/reports/TASK-083-CODEX.md`

## Base commit

`caf77e1226aafa120dd98e62f72373a6511fb3b8`
