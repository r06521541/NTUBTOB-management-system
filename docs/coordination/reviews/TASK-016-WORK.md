# TASK-016 Work Review

狀態：`accepted`

## 驗收結論

TASK-016 符合核准範圍與驗收條件，建議 Owner 接受並決定是否將 Draft PR #32 標記 ready 及 merge。本次驗收不包含部署。

## 實際查驗

- Base：`974433168b86e5638adce779ed8eccced0542094`
- Codex 最終交付 HEAD：`ab14741a31e7667fdb4b5230cb551898a31566eb`
- Branch：`codex/defer-scheduled-service-startup-effects`
- Draft PR：[#32](https://github.com/r06521541/NTUBTOB-management-system/pull/32)，狀態 `OPEN`、`DRAFT`、`MERGEABLE`
- 實際 diff 僅涵蓋兩個排程服務、其離線測試及 TASK-015／016 協作文件；未修改 `shared_lib`、schema、Secret、IAM、Scheduler 或 deployment config。

程式查驗結果：

- 兩個 app import 時不再建立 `LineBotAnnouncementHelper`，第一次業務 `announce()` 才初始化，後續於同一 process 重用。
- `notify_cronjob_service` package import 不再建立 helper，也不再執行 `announce('Hi')`。
- `/healthz` 維持無 DB／通知副作用；既有 business route、訊息內容及 recipient selection 未改。
- 測試會在 constructor 於 import 時被呼叫時失敗，並涵蓋 lazy initialization、重用及訊息轉送。

## 驗證證據

- 本機 Python 3.12.13：game broadcast `27/27` 通過。
- 本機 Python 3.12.13：notify cron `8/8` 通過。
- `python -m compileall -q apps/game_broadcast_service apps/notify_cronjob_service`：通過。
- `git diff --check 974433168b86e5638adce779ed8eccced0542094..ab14741a31e7667fdb4b5230cb551898a31566eb`：通過。
- GitHub Actions Python 3.10.20：run `30975715544`、job `92209168322`，game `27/27`、notify `8/8`、schedule `5/5` 全數通過。

## 風險與邊界

- 首次業務通知才進行 LINE group DB query；若當時 DB 不可用，既有錯誤仍會在該業務請求發生。
- Lazy cache 未加鎖；同一 process 的首次請求若真正並行，理論上可能重複建立 helper。Helper 建構本身不發訊息，且既有排程為 nonoverlapping，因此列為非阻擋風險。
- Health check 僅證明程序與 route 存活，不代表 DB 或 LINE 可用。
- 驗收期間未部署、未呼叫 production、未連 production DB、未發送通知，也未操作 Secret、IAM、Scheduler 或正式資料。

## Work 建議

`accepted`。下一位角色為 Owner；若 Owner 接受，可另行明確授權將 PR #32 標記 ready 並 merge。任何 production deployment 仍需獨立批准。
