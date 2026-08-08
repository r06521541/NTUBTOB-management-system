# TASK-079 Work 驗收

## 結論

`accepted_pending_hosted_ci`

TASK-079 的 repository 變更符合範圍；可建立唯一 ready PR，等待最小充分的 hosted CI 後依既有 Git standing authorization
合併。這不構成任何 production deployment 授權。

## 實際查驗

- Branch：`codex/line-token-pin-notify-feature-off`
- Base：`1838ec6fc77a74e23700f9cd29b8ea910c0a29fb`
- Implementation：`9bc188649915c91e410609e85e140b2caa7a26aa`
- Completion／handoff：`6e941dd6b6237abb3da80210c218087ebda2ef0b`
- 驗收時工作樹：乾淨。
- 實際 diff 僅包含兩份 active Cloud Build config、兩份直接 deployment-contract tests、Codex report 與 handoff；
  沒有 private env、Secret payload、runtime flag、schema、shared library 或部署工具行為變更。

## 驗收條件

- 通過：兩份 active config 都將 `CHANNEL_ACCESS_TOKEN` 綁定到 Secret version 2。
- 通過：兩份 contract test 都明確要求 version 2，且拒絕 version 1。
- 通過：以 `rg -g cloudbuild.yaml` 搜尋，沒有 active Cloud Build config 留下 version-1 binding。
- 通過：私有服務的 `--no-allow-unauthenticated` 與 env-file credential filter 契約未被削弱。
- 通過：未發現範圍外 diff 或外部操作證據。

## Work 獨立驗證

以 workspace bundled Python 執行：

```text
python -m unittest \
  apps.game_broadcast_service.tests.test_deployment_contract \
  apps.notify_cronjob_service.tests.test_deployment_contract \
  tools.tests.test_deploy_scheduled_service -v
```

結果：25 passed。

另已執行：

```text
python -m compileall -q \
  apps/game_broadcast_service/tests/test_deployment_contract.py \
  apps/notify_cronjob_service/tests/test_deployment_contract.py
rg -n -g cloudbuild.yaml "CHANNEL_ACCESS_TOKEN=CHANNEL_ACCESS_TOKEN:1" .
git diff --check 786b2ef..HEAD
```

compileall 與 diff check 通過；config 搜尋沒有結果。此輪沒有 Python 邏輯變更，故不執行 bundled Windows Black CLI。

## 尚未驗證與下一步

- 尚未執行 Cloud Build、部署或 production Secret metadata／payload 讀取；不宣稱線上設定因 repository 修正而改變。
- Hosted CI 是合併前唯一剩餘 gate。
- 合併後的 notify Phase C feature-off source deployment 仍須另立 deployment task，盤點 exact source、artifact、revision、
  flags 與 rollback，並取得 Owner 明確批准。
