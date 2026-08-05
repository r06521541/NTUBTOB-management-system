# Web Portal Runtime Secrets Bootstrap（2026-08-06）

## 結果

TASK-026已完成。兩個Web Portal專用Secret resources已建立且各有一個enabled version：

| Runtime key | Secret reference | Version state |
| --- | --- | --- |
| `LINE_LOGIN_CHANNEL_SECRET` | `web-portal-line-login-channel-secret:1` | `enabled` |
| `SECRET_KEY` | `web-portal-session-secret-key:1` | `enabled` |

Runtime service account `556891917512-compute@developer.gserviceaccount.com`的既有project-level `roles/secretmanager.secretAccessor`已用欄位最小化查詢確認。

## 安全輸入

- LINE Login Channel Secret由Owner在本機PowerShell hidden prompt親自輸入。
- Flask session key由本機cryptographically secure RNG產生。
- Payload只經process memory與stdin送入Secret Manager，沒有放入command argument、repository、`.env.yaml`或暫存檔。
- Work沒有執行`gcloud secrets versions access`、沒有讀回或顯示任何payload。
- 一次性本機腳本已於metadata驗證成功後移除，未加入Git。

## Metadata證據

- Project：`ntubtob-schedule-405614`
- `projects/556891917512/secrets/web-portal-line-login-channel-secret`：version `1`、`enabled`、建立時間`2026-08-05T15:59:55Z`
- `projects/556891917512/secrets/web-portal-session-secret-key`：version `1`、`enabled`、建立時間`2026-08-05T16:00:05Z`
- Runtime accessor role：`roles/secretmanager.secretAccessor`

## 尚未發生

- 兩個Secrets尚未綁定至Cloud Run revision。
- Production仍由既有`web-portal-00026-rtc`承接流量，TASK-023盤點時的plain env狀態尚未因本任務改變。
- 未執行Web Portal build、deploy、traffic切換、HTTP／LINE Login smoke、DB操作或通知。
- 未修改IAM、Secret version state或其他Secret resources。

## 下一步前置條件

下一個Web Portal deployment工作包可使用exact references：

- `WEB_PORTAL_LINE_LOGIN_SECRET_REF=web-portal-line-login-channel-secret:1`
- `WEB_PORTAL_SESSION_SECRET_REF=web-portal-session-secret-key:1`

部署前仍需Owner提供或確認非Secret的`WEB_PORTAL_ADMIN_MEMBER_IDS`，並另行批准build、deploy、驗證與rollback範圍。新Session Secret首次部署會使既有Web Portal登入session失效，使用者需重新登入。

