# TASK-069：部署 Web Portal identity maintenance guard

## 目標

將已合併且通過 CI 的 TASK-068 commit 部署至 production `web-portal`，使 legacy Member／LINE identity
配對與忽略操作在未明確啟用 maintenance flag 時由 server-side guard fail closed。

## 精確工作包

- Project／region：`ntubtob-schedule-405614`／`asia-east1`
- Service：`web-portal`
- Approved commit：`44acdcd1576be57fe2d9c08861872fa75146a2ef`
- Previous healthy／rollback revision：`web-portal-00039-87s`
- LINE Login Secret reference：`web-portal-line-login-channel-secret:1`
- Session Secret reference：`web-portal-session-secret-key:1`
- `WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED` 保持不存在，依程式 default-off；不得在本任務設為 `true`。

## 允許範圍

- 依 deployment runbook 執行 repository preflight、Cloud Build、Cloud Run rollout。
- 唯讀驗證 revision、traffic、image digest、runtime Secret classification、runtime identity、public IAM 與錯誤 logs。
- 各一次無副作用 `GET /` 與 `GET /demo/`。
- 若 wrapper 定義的 rollout 閘門失敗，將 100% traffic rollback 至 `web-portal-00039-87s`。

## 非目標

- 不人工登入、配對、忽略或操作管理 POST。
- 不讀寫 production DB、不發送 LINE／Discord 通知。
- 不修改 Secret、IAM、Scheduler、schema、RLS 或其他服務。
- 不啟用 transactional dual-write；TASK-068 guard 保持關閉。

## 驗收條件

1. 新 revision Ready 且承接 100% traffic，image 對應 approved commit。
2. 三項既有 runtime Secret 維持 Secret Manager reference，public invoker 邊界不變。
3. Maintenance flag 不存在或為 false；production match／ignore 維持 fail closed。
4. `GET /` 回應 200、`GET /demo/` 回應 404。
5. 新 revision 無部署期間 ERROR logs；temporary deployment env 已清除。
6. 未執行非目標中的外部副作用。

## 執行結果

- Cloud Build：`e8534be4-cb7a-4efc-814d-ba4fa735ccf4`
- New revision：`web-portal-00040-wm9`
- Image digest：`sha256:1c4ec082515fd0369ead487ccf02137fa76b42fb666bf4fae47a90a78c6cf01c`
- 結果：成功，100% traffic 已切至新 revision；rollback 未觸發。
