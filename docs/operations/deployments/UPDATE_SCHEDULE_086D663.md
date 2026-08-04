# Update Schedule Production Deployment Package

Status：`deployed_successfully`
Task：`TASK-010`
Target：production `update-game-schedule`
Commit：`086d663831cf49ddaa5f8413edd8508d1f6bf596`

Expected outcome：team and inclusive date filters remain combined before production schedule comparison/write.

TASK-011 prepared a generation-specific recovery path using the official Cloud Functions v2 API. The immutable source generation exists and bucket versioning is enabled. The recovery request has not been exercised because doing so would mutate production; it may be executed only under explicit TASK-010 rollback authorization.

Rollback source：`gs://gcf-v2-sources-556891917512-asia-east1/update-game-schedule/function-source.zip`, generation `1741711972938401`。See `docs/operations/GEN2_FUNCTION_ROLLBACK.md`.

## Deployment evidence

- Deployed at：2026-08-05 00:33 Asia/Taipei。
- Build：`7d26952d-f9d3-4a40-a941-26db20630636`（`SUCCESS`）。
- Revision：`update-game-schedule-00028-bij`。
- Image digest：`sha256:1a6cea978ad987425359cb70efddf6a3b22c1de0af5d4f4a8a8c77a920547885`。
- Resolved source generation：`1785861160031448`。
- Function state：`ACTIVE`；revision Ready／Active／ContainerHealthy／ContainerReady。
- Runtime／entry point：Python 3.10／`main`。
- Authentication：function 與 underlying Cloud Run service 均沒有 public IAM binding。
- Existing Secret reference、service account、resource limits與 traffic policy未變。
- Scheduler：`UpdateGameSchedule` 維持 enabled、`0 10,16 * * *`、Asia/Taipei、原 URI 與 OIDC service account。

## Verification boundaries

- 沒有人工 invoke、Crawler call 或人工 production DB write。
- 沒有修改 Scheduler、IAM、Secret 或其他服務。
- 沒有讀取 Secret value或 application logs。
- 部署工具曾在 terminal 回顯既有非密碼 environment settings；這些值未寫入本紀錄。
- 本機離線測試 5/5 通過；本機 bundled runtime 為 Python 3.12，Python 3.10 依既有 GitHub Actions 證據。
- 沒有觸發 rollback；generation-specific recovery request仍為 prepared but unexercised。
