# TASK-091 Codex report

## Implementation

- Implementation commit: `cd896a565afed1dbd8688bb9c3e7af5b29d6d83e`; correction commit: `e0a632e418c9afd5bf7df33229a973c4d89c7e75`。
- Changes-requested correction：新增 `person_directory` 低敏 projection；`/manage/people` 不再呼叫管理 dashboard。
- 建立 Basic／Officer／Admin capability contract：低敏 Person directory、Person 編輯、pending identity、qualification/access 管理與通知 prepare/confirm/send 分層。
- 新管理入口改以 capability policy enforcement；既有 production principal 仍只解析 member／allowlist admin。
- 新增非 production 瀏覽器與 LINE in-app browser smoke 準備及證據格式；通知 smoke 明確為 dry-run、不發送。

## Verification

- Verification：Web Portal unittest 129 passed、2 skipped；py_compile 通過；git diff --check 通過。
- Shared portal-data contract tests：24 passed、12 skipped；phase-c lifecycle tests：3 passed、24 skipped。
- Black 逐檔 API check 通過；isort 比對確認三個受影響 Python 檔的 would-reformat 為既有 baseline，未改動無關 import。
- 未執行 production、部署、Secret、正式 DB、IAM、Scheduler 或真實通知操作。
