# Web Portal Production Deployment Readiness（2026-08-05）

## 結論

目前**不適合部署**Web Portal。Cloud Run本身健康、公開邊界與callback URL一致，也有可辨識的rollback revision；但TASK-022要求的LINE Login channel secret與Flask session key之Secret Manager resources不存在可安全唯一辨識的候選，因此無法組成fail-closed deployment參數。

本次只執行Owner批准的欄位最小化唯讀查詢；未讀取Secret／plain env values、未呼叫服務URL、未部署或修改任何GCP資源。

## 已確認事實

### 操作者與目標

- Active account：`yces3108@gmail.com`
- Project：`ntubtob-schedule-405614`
- Cloud Run預設region：未設定；所有本次查詢均明確指定`asia-east1`，未修改本機config。
- Target：`web-portal`

### Current production service

- Service URL：`https://web-portal-7uz453jt3a-de.a.run.app`
- Latest created／ready revision：`web-portal-00026-rtc`
- Traffic：`web-portal-00026-rtc`承接100%
- Ready：`True`
- Image digest：`sha256:2d775811e40d62479f4a707034a31b14681ca3b65111220bc284b0bb450adcef`
- Revision建立時間：`2025-03-11T16:49:18.391568Z`
- Runtime service account：`556891917512-compute@developer.gserviceaccount.com`
- Ingress：`all`
- `allUsers`具有`roles/run.invoker`：是；目前service為public
- Runtime service account具有project-level `roles/secretmanager.secretAccessor`：是

### Runtime設定分類

以下只記錄key的注入方式，沒有讀取或保存value：

| Key | 分類 | Secret reference |
| --- | --- | --- |
| `DSN_PASSWORD` | secret-backed | `supabase-database-password:latest` |
| `LINE_LOGIN_CHANNEL_SECRET` | plain | 無 |
| `SECRET_KEY` | plain | 無 |
| `WEB_PORTAL_ADMIN_MEMBER_IDS` | absent | 無 |
| `LINE_LOGIN_CHANNEL_ID` | plain | 無 |

Project內Secret resource名稱的唯讀候選盤點未找到可唯一辨識為LINE Login channel secret或Flask session key的兩個resources。名稱相近的既有資源不得在不知道用途時挪用或猜測。

### Callback與rollback

- Repository的`LINE_REDIRECT_URI` host與目前Cloud Run service URL一致，callback path為`/line/callback`。
- 目前唯一已確認的rollback基準是仍承接100% traffic且Ready的`web-portal-00026-rtc`及上述digest。
- `origin/main`為`f7471da1fed20f6477a16d125a6347692e3e732d`；TASK-022的最終Python 3.10 PR驗證曾成功，但本次環境無法使用GitHub CLI重新查驗merge commit的獨立run。

## 推論

- 現行revision仍使用TASK-022修正前的runtime設定；若直接使用新deploy wrapper，缺少兩個必填Secret references時應在Cloud Build前fail closed。
- Public Cloud Run boundary與硬編碼callback host目前相容，但未查LINE Developers Console，因此不能確認LINE側登記仍一致。
- Project-level Secret accessor可讓runtime讀取Secret，但權限範圍偏廣；這不阻擋本次readiness判定，後續可另案縮小權限。

## Blockers與待Owner決策

1. 建立或確認一個專供`LINE_LOGIN_CHANNEL_SECRET`的Secret resource與啟用version。
2. 建立或確認一個專供Flask `SECRET_KEY`的Secret resource與啟用version。
3. 決定production `WEB_PORTAL_ADMIN_MEMBER_IDS`；只在未來部署時提供，不寫入repository或本報告。
4. 在上述resources確定後，另行批准只查其version metadata與runtime accessor，再產生exact deployment工作包。
5. 部署批准需另外決定是否允許一次不含LINE Login／DB操作的HTTP smoke；本次沒有呼叫production URL。

## 下一步建議

建立小型TASK-024「Web Portal runtime Secrets bootstrap」。先由Owner決定兩個新的resource名稱與安全的payload寫入方式；任何Secret建立、version新增或IAM修改都必須另行精確批准。完成後再回到Web Portal deployment工作包。

建議resource名稱（僅為命名提案，不代表已建立）：

- `web-portal-line-login-channel-secret`
- `web-portal-session-secret-key`

## 2026-08-06更新

TASK-026已解除兩個runtime Secret resource blocker：

- `web-portal-line-login-channel-secret:1`：enabled
- `web-portal-session-secret-key:1`：enabled

Payload未被讀回或記錄，runtime accessor亦已確認。Web Portal仍未部署；下一步需另立exact deployment工作包，確認`WEB_PORTAL_ADMIN_MEMBER_IDS`並接受新Session Secret會使既有登入session失效。

## 本次未執行

- Secret payload access或plain env value讀取
- Secret／IAM／Cloud Run／traffic修改
- Docker、Cloud Build或deployment
- Production HTTP、LINE Login或DB測試
- LINE／Discord通知
