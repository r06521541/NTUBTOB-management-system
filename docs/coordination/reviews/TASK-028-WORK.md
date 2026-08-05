# TASK-028 Work 驗收報告

驗收時間：2026-08-06（Asia/Taipei）

## 驗收結論

- 結論：`accepted`
- 下一位角色：Owner
- 驗收 branch：`codex/web-portal-safe-deployment-wrapper`
- Base commit：`d48a5bad37866095bf337003bc64de091a108630`
- Implementation commit：`9d889826c5453dd7456e2b727928830bda819019`
- Codex completion commit／驗收前 HEAD：`e8dc0b48f7a04ac960927347fac43792ef8c5881`
- Repository：驗收開始及測試完成後均乾淨

## 實際 diff 查驗

- 新增 `tools/deploy_web_portal.py` 與 15 項 Web Portal wrapper unit tests。
- 保留既有 scheduled-service wrapper CLI，既有 11 項測試仍通過。
- README 與 deployment runbook 補上跨平台 dry-run、exact execution gates 與 Owner deployment approval 邊界。
- 實際 diff 未修改 application routes、templates、models、schema、Cloud Build config、IAM、Secret、Scheduler 或 production data。
- Commit 標題具描述性，TASK 編號位於 body；實作與協作文件分成兩個合理 commits。

## 驗收條件

| 條件 | 結果 | 證據 |
| --- | --- | --- |
| 預設 dry-run 且不呼叫 cloud／HTTP | 通過 | CLI 僅執行 local Git/source preflight；unit test 驗證 runner 只有兩個 Git read commands |
| `--execute` 要求四項 exact inputs | 通過 | 缺任一 input、錯誤 SHA/revision/Secret ref 均 fail closed |
| 固定 Web Portal build context | 通過 | build cwd 固定 `apps/web_portal`，無任意 service/context 參數 |
| PowerShell substitutions 不被拆分 | 通過 | subprocess argument list；完整 substitutions 為單一 argument，具 regression test |
| async bounded polling | 通過 | async submit、terminal status、malformed status、failure 與 timeout 均有測試 |
| Secret 與 temporary env 邊界 | 通過 | 三個敏感 key 過濾；既存 temp file 不覆寫；成功與重要失敗路徑清除 |
| revision／digest／traffic／IAM／runtime contract | 通過 | fake gcloud JSON 覆蓋 Ready、digest、100% traffic、public invoker、identity、Secret/plain classifications 與 demo gates |
| 最小 HTTP 驗證 | 通過 | 各一次 GET、timeout、no redirect、no body read；只接受 `/` 200 與 `/demo/` 404 |
| 精確 rollback 與結果區分 | 通過 | verification failure 只切回 validated revision；rollback success/failure 分開回報 |
| Python 3.10 相容 | 通過（離線語法） | `ast.parse(..., feature_version=(3, 10))` 通過；尚無 hosted Python 3.10 runtime 證據 |
| 文件與交棒 | 通過 | Codex report、PROJECT_STATE、README、runbook、HANDOFF 已更新 |

## Work 實際執行的驗證

```text
python -m unittest discover -s tools/tests -v
Ran 26 tests — OK

python -m unittest discover -s apps/web_portal/tests -v
Ran 45 tests — OK (skipped=2)

python -m compileall -q tools apps/web_portal
通過

ast.parse(..., feature_version=(3, 10))
通過

python tools/deploy_web_portal.py
Preflight passed for web-portal; no cloud or HTTP commands were run.

git diff --check d48a5ba..HEAD
通過
```

兩個 skip 為既有 Windows 環境缺少 Unix make/sh 的 Make contract tests；新 wrapper 的 15 項核心測試無 skip。

## Blocking 問題

無。

## 回歸風險與非阻擋事項

- 測試使用 fake runner，尚未證明實際 `gcloud --format=json` schema、Cloud Build async timing 或 production HTTP 行為；正式使用仍須另立 exact deployment work package。
- 本機 bundled runtime 為 Python 3.12.13；Python 3.10 僅完成 grammar compatibility。若進入 PR，應以 hosted Python 3.10 CI 補 runtime 證據。
- wrapper 的 `--execute` 從未執行；本次接受不構成 deployment、rollback、Secret metadata query 或 production HTTP 授權。
- 原有兩個 Unix Make contract skips 可保留；TASK-028 已讓新的核心部署流程在 Windows 完整測試，不再依賴它們。

## 安全確認

驗收期間未執行 `--execute`、未呼叫 gcloud 或 production HTTP、未讀取真實 `.env.yaml` 或 Secret payload、未部署、未 rollback、未連 DB、未發通知，也未 push、建立 PR 或 merge。
