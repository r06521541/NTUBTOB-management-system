# TASK-028 Codex 實作報告

更新時間：2026-08-06T02:55:00+08:00

## 任務狀態

- 狀態：`ready_for_review`
- branch：`codex/web-portal-safe-deployment-wrapper`
- base commit：`d48a5bad37866095bf337003bc64de091a108630`
- planning commit：`7e4415e35f75a5eba676827051a64c1d86957af5`
- implementation commit：`9d889826c5453dd7456e2b727928830bda819019`
- push／PR／CI：未授權，未執行

## 實際修改

- 新增 Python 3.10 標準函式庫 Web Portal deployment wrapper；預設只做 repository-local preflight。
- `--execute` 同時要求 exact 40-character commit、`web-portal-*` rollback revision 與兩個 Secret `resource:version` references。
- 固定 project、region、service 與 `apps/web_portal` context；所有 subprocess 使用 argument list，Cloud Build substitutions 保持單一 argument。
- 以 async Cloud Build submit、bounded polling、terminal status 驗證取代無限前景等待。
- 重建／複製 shared sdist，過濾三個敏感 env keys，並以 `finally` 清理 temporary env。
- 驗證 immutable digest、new revision Ready、100% traffic、public invoker、runtime identity、Secret/plain key classifications 與 demo gates。
- HTTP helper 禁止 redirect、不讀 response body、設定 timeout，只接受 `/` 200 與 `/demo/` 404。
- rollout 後驗證失敗只會切回 CLI 已驗證的 exact rollback revision，並區分 rollback success／failure。
- README 與 deployment runbook 補上 Windows／Unix dry-run、execute gates 與「工具不等於部署授權」警告。

## 修改檔案

- `tools/deploy_web_portal.py`
- `tools/tests/test_deploy_web_portal.py`
- `README.md`
- `docs/operations/DEPLOYMENT_RUNBOOK.md`
- `docs/coordination/reports/TASK-028-CODEX.md`
- `docs/coordination/PROJECT_STATE.md`
- `docs/coordination/HANDOFF.yaml`

## 驗證命令與結果

使用 bundled CPython 3.12.13：

```text
python -m unittest discover -s tools/tests -v
Ran 26 tests — OK
  Web Portal wrapper: 15
  existing scheduled-service wrapper: 11

python -m unittest discover -s apps/web_portal/tests -v
Ran 45 tests — OK (skipped=2)

python -m compileall -q tools apps/web_portal
通過

ast.parse(..., feature_version=(3, 10))
通過

python tools/deploy_web_portal.py
Preflight passed; no cloud or HTTP commands were run.

git diff --check
通過
```

兩個 Web Portal skips 是 Windows 沒有 `make`／`sh` 的既有 platform-specific Make contract；新 wrapper 的核心 15 項測試沒有 skip。

Black／isort 未執行：bundled Python 未安裝 repository 指定 formatter；未為此下載依賴或修改環境。

## 測試涵蓋

- dry-run 無 gcloud／HTTP、execution-only arguments fail closed、四項 exact gate。
- dirty tree、HEAD mismatch、missing tool/source、existing temp env。
- secret filtering、shared artifact build/copy、固定 context 與單一 substitutions argument。
- async working→success、failure、malformed status、bounded timeout。
- digest、Ready、traffic、public IAM、identity、Secret/plain env classification。
- HTTP 次數、status、timeout、no redirect、no body read。
- build failure、verification failure、HTTP failure、rollback success/failure 與 cleanup。
- 既有 scheduled-service wrapper tests 全數保持通過。

## 未執行與安全聲明

- 未執行 `--execute`。
- 未呼叫 gcloud、Cloud Build、Cloud Run、Artifact Registry、Secret Manager 或 production HTTP。
- 未讀取或輸出任何真實 `.env.yaml` value、Secret payload或管理者 ID。
- 未部署、rollback、push、建立 PR、merge，亦未修改 IAM、Secret、Scheduler、DB、schema 或 production data。
- 未呼叫 LINE／Discord、LINE Login callback 或其他外部服務。

## 未驗證風險與假設

- Fake runner 驗證 repository orchestration，不能證明實際 gcloud JSON schema、Cloud Build async timing、Cloud Run metadata 或 production HTTP 正確。
- Python 3.10 只完成 grammar compatibility；因本輪禁止 push／PR，沒有 hosted Python 3.10 CI 證據。
- Wrapper 以部署前 baseline runtime identity 作為應保持值；正式執行仍須 Owner 的 exact deployment work package 與 runbook preflight。
- Web Portal production execution、Secret metadata/IAM 與 rollback revision 可用性仍需另行批准並在執行當下確認。

## 未提交修改與 Owner 決策

本報告、PROJECT_STATE 與 HANDOFF 將形成最後一個本機協作 commit。完成後工作樹預期乾淨；不需要 Owner 對實作內容做新決策，下一步由 Work 獨立驗收。
