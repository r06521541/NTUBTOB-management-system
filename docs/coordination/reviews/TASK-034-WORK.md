# TASK-034 Work 驗收報告

驗收時間：2026-08-06（Asia/Taipei）

## 結論

- 結果：`accepted`
- Branch：`codex/promote-web-portal-traffic`
- Base：`96ee2a0d8fefce74b35b410069f0e1bafb405eeb`
- Implementation：`b7d13bc`、`05ef544`
- Codex completion：`06016b9`
- Draft PR：[#43](https://github.com/r06521541/NTUBTOB-management-system/pull/43)
- 下一位角色：Owner（決定是否 squash merge；production deployment 仍須另行批准）

## 驗收結果

- Revision readiness 與 traffic convergence 已拆成兩個 bounded polling 階段。
- 新 revision 必須不同於 baseline、Ready，且通過 image digest、runtime identity、Secret／plain env classification 與 production demo gate 檢查，才可切換 traffic。
- Pinned old traffic 情境會以固定 project、region、service 與 exact new revision 執行一次 100% traffic promotion；命令仍使用 argument list 與 `shell=False` runner boundary。
- Promotion 前的 timeout 或 hard drift 不會執行 rollback mutation，原本健康的舊 traffic 保持不變。
- Promotion 開始後的 command failure、traffic timeout、IAM 或 HTTP failure，會 rollback 至 exact approved old revision；rollback failure 仍可獨立辨識。
- Traffic 尚未收斂前不查 IAM、不呼叫 HTTP；temporary env 在成功與失敗路徑均由 `finally` 清理。
- 已在新 revision 本來就是 100% traffic 時避免重複 promotion。

## Work 獨立驗證

```text
tools tests: 41 passed
Web Portal tests: 58 passed, 2 existing Windows make/sh skips
compileall tools/apps/web_portal: passed
Web Portal dry-run: passed; no cloud or HTTP
git diff --check 96ee2a0..HEAD: passed
working tree before review docs: clean
GitHub Python 3.10 CI run 31044107364 / job 92435301494: success
PR #43: open, Draft, mergeable
```

## 尚未驗證與風險

- 所有 deployment 行為僅由 fake runner／mock 驗證；尚未對真實 Cloud Run 執行 promotion。
- `update-traffic` command failure 採保守策略嘗試 rollback，因 command failure 無法證明 server 端完全未接受變更。
- IAM 仍只查一次；若 IAM control plane 暫時延遲，流程會 fail closed 並 rollback。
- Windows 本機缺少 `make`／`sh`，兩項既有 deployment contract 測試維持 skip；GitHub hosted runner workflow 已成功。
- 本次沒有部署、gcloud／HTTP 呼叫、production traffic mutation、Secret／IAM／DB／schema／LINE 操作。

## 建議

接受 TASK-034，可將 PR #43 標記 ready 並以 squash merge 合併。合併不代表部署授權；若要再次 rollout，應以 merge 後的 exact main commit 建立新的 production deployment 工作包，執行前重查目前 100% traffic revision 作為 rollback target，且外層執行 timeout 必須長於 wrapper 的 bounded timeout。

## Owner 核准與 production 結果

- Owner 後續明確授權 ready、squash merge 與 deployment。
- PR #43 squash merge commit：`bb91d9e5d695de2a4601bfa4c98e0de3f25f0e94`。
- Cloud Build ID：`3dd2589d-1efc-44f7-9b83-c387a4aaa389`。
- 新 revision：`web-portal-00032-f7z`，Ready，100% traffic。
- Image digest：`sha256:d86c38178d35da30c36d3ce007d95f254a51d413a7d46a7d68e6b5c698662aeb`。
- 無副作用驗證：`GET /` 200、`GET /demo/` 404。
- Rollback target 經部署前確認為 `web-portal-00027-fwf`；本次未觸發 rollback。
- 部署後獨立 control-plane 查核與 temporary env cleanup 均通過。
