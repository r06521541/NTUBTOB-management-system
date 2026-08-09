# TASK-001 Work 驗收報告

驗收時間：2026-08-04T01:38:07+08:00
驗收者：Work
驗收結論：`accepted`
下一位角色：`owner`

## 1. 驗收基準

- branch：`fix/weather-api-secret`
- task base commit：`f1884bfbe903e4b24fa82ae6cf19c86167d06ee2`
- 驗收 HEAD：`f1884bfbe903e4b24fa82ae6cf19c86167d06ee2`
- Codex 沒有建立 commit；成果為未提交、未追蹤檔案。
- Repository 不乾淨：
  - 既存 Owner/Work 檔案：`AGENTS.md`、`docs/coordination/` 中的協作、狀態與任務文件。
  - TASK-001 實作：`apps/game_broadcast_service/tests/test_deployment_contract.py`。
  - Codex 交付：`docs/coordination/reports/TASK-001-CODEX.md` 與 `HANDOFF.yaml` 更新。
- 沒有 tracked file diff；Work 已直接讀取並查驗全部未追蹤任務檔案，沒有只依賴 Codex 摘要。

## 2. 實際修改查驗

新增的 `test_deployment_contract.py`：

- 只使用 Python standard library：`pathlib`、`re`、`unittest`。
- 直接讀取 repository 中的 `cloudbuild.yaml`、`.dockerignore` 與 `makes/deploy_apps.mk`。
- 有 4 個測試，分別驗證必要 Secret bindings、LINE credential filter、`.env.yaml` Docker ignore 與 Cloud Run private flag。
- 沒有修改 application、deployment config、Makefile、requirements、資料庫或通知邏輯。
- 沒有讀取真實 `.env.yaml`，沒有外部 API、資料庫、GCP、LINE、Discord 或 weather 呼叫。

## 3. 驗收條件逐項結果

| 驗收條件 | 結果 | 證據 |
| --- | --- | --- |
| 直接檢查實際 Cloud Build、Docker ignore、deployment Makefile | 通過 | 測試的 file constants 指向三個 repository 實檔。 |
| 移除任一必要 Secret binding 會失敗 | 通過 | 三個變數以 subtest 逐一檢查；Work 另以 in-memory mutation 移除 LINE binding，測試如預期失敗。 |
| 移除 LINE token/secret filter 會失敗 | 通過 | 測試解析 game broadcast target 的實際 `grep -vE` pattern；Work mutation 移除 `CHANNEL_SECRET` 後如預期失敗。 |
| 移除 `.env.yaml` Docker ignore 會失敗 | 通過 | Work mutation 移除該行後測試如預期失敗。 |
| 改為 unauthenticated 會失敗 | 通過 | Work mutation 將 private flag 改為 public 後測試如預期失敗。 |
| 既有 13 個 reminder tests 仍通過 | 通過 | 完整 suite 共 17 tests，全部通過。 |
| 測試完全離線 | 通過 | 新測試只讀文字檔；既有測試使用 stub/mock。 |
| Python 3.10 相容性 | 限制下通過 | `ast.parse(feature_version=(3, 10))` 通過；3.10 runtime 無法啟動。 |
| `git diff --check` | 通過 | tracked diff check 無錯；未追蹤任務檔另做 trailing-whitespace 檢查，無錯。 |
| diff 僅限任務範圍 | 通過 | 除既存 Owner/Work 文件外，只新增測試、Codex report 並更新 handoff。 |
| Codex report 符合最低要求 | 通過 | 包含狀態、base/head、修改、命令、測試、未測事項、假設、風險、working tree 與部署/Secret 影響。 |

## 4. Work 獨立測試證據

### 完整 suite

```text
C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe \
  -m unittest discover -s apps/game_broadcast_service/tests -v
```

- Runtime：Python 3.12.13
- 結果：17 tests passed，包含 4 個新測試與 13 個既有測試。

### 回歸敏感度

Work 以 in-memory mutation 分別模擬移除 LINE token binding、LINE secret filter、`.env.yaml` ignore，以及把 Cloud Run private flag 改為 public；四種 mutation 均被對應測試捕捉。

### Python 3.10

- 3.10 grammar check：通過。
- Windows Python launcher 列出 3.10 registration，但執行 `py -3.10 --version` 失敗，錯誤為無法建立指向 WindowsApps 的 Python 3.10 process。
- 因此沒有 Python 3.10 runtime 的實際 unittest 證據，不能宣稱已在 3.10 執行。

### 格式與 working tree

- `git diff --check`：通過；目前沒有 tracked diff。
- 未追蹤的 test/report/handoff 另做 trailing-whitespace 檢查：通過。
- Black 未安裝於 bundled Python；Codex 的 `black --check` 未能執行。Work 查驗新增測試格式與鄰近測試一致，未發現需阻擋的格式問題。

## 5. 回歸風險

- 測試以文字語意解析 shell command/Make target，部署格式大幅重排時可能需要同步調整測試。
- 靜態測試不能證明 Secret version、IAM、Cloud Build、image layer 或 Cloud Run revision 在線上正確。
- Python 3.10 runtime 與 Black formatter 尚未實際驗證。
- 所有成果仍未提交；Owner 接受後仍需決定是否 stage/commit。這不等於批准部署。

## 6. Blocking 問題

無。

## 7. 非阻擋建議

- 後續建立 CI 時，以 Python 3.10 跑完整 suite，補足 runtime 證據。
- Windows 驗證流程在判定 Python 版本不可用前，應同時檢查 launcher registration 與實際啟動結果。
- 未來若部署檔改為結構化工具產生，可再評估更語意化的驗證；現階段不需新增 dependency。

## 8. 驗收結論

`accepted`

TASK-001 已符合需求且沒有 blocking issue。建議交由 Owner 決定接受結案、是否將目前未追蹤的協作文件與測試納入 commit，以及後續是否建立 Python 3.10 CI。此結論不包含 production deployment、Secret 操作或真實 LINE/Discord 驗證的批准。
