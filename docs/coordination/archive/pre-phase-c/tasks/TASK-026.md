# TASK-026：Web Portal Runtime Secrets Bootstrap

狀態：`completed`
優先級：P1 security／deployment readiness
規劃者／執行者：Work（需Owner在終端機提供LINE Login Channel Secret）
Base commit：`cdb67bf007ec67d882c6e974143a4d527f1528cd`

## 1. 任務目標

在GCP project `ntubtob-schedule-405614`中建立兩個Web Portal專用Secret Manager resources及各一個enabled version，讓後續Cloud Run deployment可把`LINE_LOGIN_CHANNEL_SECRET`與Flask `SECRET_KEY`改為runtime Secret references。

本任務只bootstrap Secret resources並做metadata驗證；不部署Web Portal、不修改Cloud Run env／traffic、不呼叫production URL、不測LINE Login，也不修改IAM、資料庫或schema。

## 2. 背景與已確認事實

- TASK-022已合併runtime Secret binding與fail-closed deployment preflight。
- TASK-023唯讀盤點確認production `web-portal-00026-rtc`仍把`LINE_LOGIN_CHANNEL_SECRET`及`SECRET_KEY`以plain env注入。
- Project內沒有可安全唯一辨識為上述用途的兩個Secret resources。
- Runtime service account `556891917512-compute@developer.gserviceaccount.com`目前具有project-level `roles/secretmanager.secretAccessor`；本任務不修改或縮限IAM。
- PR #37已合併為`cdb67bf`；demo功能預設關閉，不解除TASK-023 deployment gate。

## 3. 精確資源名稱

- `web-portal-line-login-channel-secret`
- `web-portal-session-secret-key`

若任一名稱已存在，立即停止，不新增version、不覆寫、不猜測其內容或用途，先交回Owner。

## 4. Secret來源與安全輸入

### 4.1 LINE Login Channel Secret

- 必須由Owner從LINE Developers Console的**LINE Login channel**取得。
- 不得使用Messaging API／webhook的`CHANNEL_SECRET`代替。
- Owner不得把值貼入聊天、command argument、clipboard紀錄文件、repository或`.env.yaml`。
- 執行時使用終端機互動式hidden input；值只在process memory短暫轉換並以stdin送至`gcloud secrets versions add --data-file=-`。
- Work不得回顯、記錄、讀回或驗證payload內容，只能確認Owner完成輸入與version metadata為enabled。

### 4.2 Flask Session Secret Key

- 在本機以cryptographically secure RNG產生至少32 bytes，直接以stdin送入Secret Manager。
- 不顯示值、不寫暫存檔、不放入shell history／command argument／repository。
- 不沿用目前production plain env value；新key會在未來deployment時使既有登入session失效，該影響在deployment task另行批准。

## 5. Owner批准後的操作白名單

所有cloud commands必須明確指定`--project=ntubtob-schedule-405614`。

1. 唯讀確認active account與project；不修改gcloud config。
2. 唯讀確認兩個exact Secret resource names不存在。
3. 建立上述兩個Secret resources，replication policy採`automatic`。
4. 對LINE Login Secret執行一次互動式hidden input並新增一個version。
5. 對Session Secret以本機secure RNG新增一個version。
6. 只查兩個resources的name、replication metadata及latest version number／state／create time。
7. 只確認runtime service account的既有Secret accessor仍有效；不輸出完整IAM policy或無關members。
8. 更新readiness與coordination文件並建立local commit。

禁止執行`gcloud secrets versions access`或任何Secret payload讀回。

## 6. 失敗與停止條件

- Active account或project不符合預期。
- Exact resource name已存在。
- Owner無法確認輸入來自正確的LINE Login channel。
- Hidden-input／stdin方式可能回顯、記錄或寫入檔案。
- Secret resource建立成功但新增version失敗：停止並保留空resource，回報狀態；不得自行刪除、重試不同payload或修改IAM。
- Version state不是enabled，或runtime accessor無法確認。
- 任何步驟要求讀取payload、修改Cloud Run／IAM、部署、LINE Login測試或production DB。

## 7. 驗收條件

- 兩個exact Secret resources存在且各有一個enabled version。
- LINE值由Owner在hidden prompt親自提供，session key由secure RNG產生；沒有值出現在console output、Git、檔案或對話。
- Runtime identity的既有accessor binding經欄位最小化唯讀確認。
- 沒有`versions access`、Cloud Run／IAM mutation、deployment、production HTTP、DB或通知操作。
- 產出metadata-only操作紀錄與下一個Web Portal deployment work package所需的exact references：
  - `web-portal-line-login-channel-secret:<VERSION>`
  - `web-portal-session-secret-key:<VERSION>`
- `git diff --check`通過且working tree只含本次文件。

## 8. Rollback與復原邊界

- 本任務尚未把Secret綁定到Cloud Run，因此建立resource／version不會改變目前服務行為。
- 本任務不批准刪除、disable或destroy Secret version；若建立後發現問題，保留未使用resource並交回Owner另行決策。
- 真正部署時的rollback仍是把100% traffic切回`web-portal-00026-rtc`；該操作不屬於本任務。

## 9. 不包含

- Web Portal build、deploy、traffic、revision或env修改。
- Secret payload讀取、顯示、複製、輪替、disable、destroy或delete。
- IAM新增／刪除／縮限。
- `WEB_PORTAL_ADMIN_MEMBER_IDS`查詢或設定。
- Production LINE Login、HTTP、DB、notification或crawler操作。
- Schema、migration、Flutter API或其他服務修改。
- Push、PR或merge；本任務預設只產生local metadata文件commit。

## 10. 需要Owner批准的精確文字

若Owner同意執行，請批准：

> 批准TASK-026依文件第5節在project `ntubtob-schedule-405614`建立兩個exact Secret resources及各一個version；LINE Login Channel Secret由我在hidden terminal prompt親自輸入，session key由本機secure RNG產生。批准metadata-only驗證與local文件commit；不批准Secret讀回、IAM／Cloud Run修改、部署、production request／DB、通知、delete／disable／destroy、push或PR。
