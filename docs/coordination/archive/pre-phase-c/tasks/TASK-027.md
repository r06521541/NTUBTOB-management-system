# TASK-027：Web Portal Production Deployment

狀態：`completed`
優先級：P1 security rollout
規劃者／執行者：Work
Base commit：`31a13e1`
Approved deployment source：`cdb67bf007ec67d882c6e974143a4d527f1528cd`

## 1. 任務目標

將已合併且Python 3.10 CI成功的Web Portal source `cdb67bf`建置為immutable image並部署至production Cloud Run `web-portal`，把database password、LINE Login Channel Secret與Flask Session Secret改為runtime Secret references，同時帶入Owner已在local正式env檔設定的`WEB_PORTAL_ADMIN_MEMBER_IDS`。

部署後只做control-plane、runtime metadata與兩個無副作用HTTP GET驗證；不執行LINE Login callback、管理POST、DB頁面、通知或其他外部整合測試。

## 2. 精確目標

- GCP project：`ntubtob-schedule-405614`
- Region：`asia-east1`
- Cloud Run service：`web-portal`
- Approved source／image tag：`cdb67bf007ec67d882c6e974143a4d527f1528cd`
- LINE Login Secret reference：`web-portal-line-login-channel-secret:1`
- Session Secret reference：`web-portal-session-secret-key:1`
- Database Secret reference：既有`supabase-database-password:latest`
- Current／rollback revision：`web-portal-00026-rtc`
- Expected service URL：`https://web-portal-7uz453jt3a-de.a.run.app`
- Expected public boundary：`allUsers`具`roles/run.invoker`
- Expected runtime identity：`556891917512-compute@developer.gserviceaccount.com`

## 3. 已確認前置條件

- PR #37已merge為`cdb67bf`；最新Python 3.10 run `31022009347`／job `92360824095`成功。
- Work已確認目前`apps/web_portal`與`shared_lib`相對`cdb67bf`沒有tracked source差異；其後local commits只有文件。
- TASK-023確認目前revision `web-portal-00026-rtc` Ready並承接100% traffic，image digest為`sha256:2d775811e40d62479f4a707034a31b14681ca3b65111220bc284b0bb450adcef`。
- TASK-026確認兩個exact Web Portal Secrets version `1`均enabled，runtime identity具既有Secret accessor。
- Owner已確認在`envs/web_portal/.env.yaml`設定`WEB_PORTAL_ADMIN_MEMBER_IDS`；Work不讀取、顯示或記錄其value。
- Repository deployment contracts保證三個runtime Secrets不進temporary plain env，Docker context排除`.env.yaml`，且production不設定demo gates。

## 4. 部署影響與Owner接受事項

- 新`SECRET_KEY`生效後，所有既有Web Portal登入session會失效，使用者需要重新LINE登入。
- `LINE_LOGIN_CHANNEL_SECRET`改由Secret Manager注入；若Owner輸入錯誤channel secret，LINE callback會失敗，control-plane與首頁GET無法偵測。
- `/match-member`部署後需要有效LINE session且Member ID位於`WEB_PORTAL_ADMIN_MEMBER_IDS`；錯誤設定會fail closed，但一般頁面不因此鎖住。
- Demo程式會存在container image，但production不設定`WEB_PORTAL_ENV=development`及`WEB_PORTAL_DEMO_MODE=true`，因此所有`/demo/*`必須回404。
- 原有首頁、LINE Login、attendance、future games、game roster與member matching routes仍保留；本任務不改schema或正式資料。

## 5. 批准後執行步驟

### 5.1 Preflight（唯讀／本機）

1. 確認active account、project與explicit region／target符合第2節；不修改gcloud config。
2. 確認working tree沒有非本任務變更，`apps/web_portal`與`shared_lib`仍與`cdb67bf`一致。
3. 確認PR #37 merged、candidate SHA存在於`origin/main`、Python 3.10 CI成功。
4. Metadata-only確認兩個Secret version `1`均enabled；禁止payload access。
5. Owner提供的事實作為`WEB_PORTAL_ADMIN_MEMBER_IDS`已設定證據；不得讀取或輸出env file內容／value。
6. 重新執行Web Portal tests、compile、deployment contracts與`git diff --check`。
7. 欄位最小化重查current revision Ready／traffic 100%、public boundary、runtime identity與rollback digest；若與第2／3節漂移則停止。

### 5.2 Build與Deploy

從repository root執行既有target，精確參數為：

```text
make deploy-web-portal \
  IMAGE_TAG=cdb67bf007ec67d882c6e974143a4d527f1528cd \
  WEB_PORTAL_LINE_LOGIN_SECRET_REF=web-portal-line-login-channel-secret:1 \
  WEB_PORTAL_SESSION_SECRET_REF=web-portal-session-secret-key:1
```

Windows環境須使用repository既有可用的Unix-like make環境；不得為了部署臨時改Makefile／Cloud Build。Target會：

- 重建shared library artifact。
- 產生排除`DSN_PASSWORD`、`LINE_LOGIN_CHANNEL_SECRET`與`SECRET_KEY`的temporary env file。
- 以Git SHA image tag執行Cloud Build／push。
- 部署public Cloud Run service並綁定三個runtime Secrets。
- 由trap在成功或失敗時移除`apps/web_portal/.env.yaml`。

記錄Cloud Build ID、image digest、新revision、Ready狀態與traffic；不得輸出env values或完整resource dump。

### 5.3 部署後驗證

1. 新revision Ready且承接100% traffic；latest created／ready一致。
2. Image reference使用approved SHA tag並記錄digest。
3. Service仍為public、ingress `all`、runtime identity不變。
4. Runtime key只分類為：
   - `DSN_PASSWORD`：secret-backed `supabase-database-password:latest`
   - `LINE_LOGIN_CHANNEL_SECRET`：secret-backed `web-portal-line-login-channel-secret:1`
   - `SECRET_KEY`：secret-backed `web-portal-session-secret-key:1`
   - `WEB_PORTAL_ADMIN_MEMBER_IDS`：present／plain；禁止顯示value
   - `WEB_PORTAL_ENV`／`WEB_PORTAL_DEMO_MODE`：不得是啟用demo的組合
5. 發出一次unauthenticated `GET /`，只接受HTTP 200；此route只render template，不查DB或外部服務。
6. 發出一次unauthenticated `GET /demo/`，只接受HTTP 404，以證明production demo fail closed。
7. 不呼叫`/line/login`、`/line/callback`、`/attendance`、`/future-games`、`/game-roster`、`/match-member`或任何POST。
8. 確認temporary `apps/web_portal/.env.yaml`已移除，working tree沒有credential artifact。

## 6. Rollback觸發條件

任一條成立時停止後續驗證，立即把100% traffic rollback至`web-portal-00026-rtc`：

- Cloud Build或deploy command失敗但Cloud Run已建立新revision／改變traffic。
- 新revision非Ready、startup／container health失敗或無法承接100% traffic。
- Image tag／digest無法對應approved source。
- Public IAM、ingress或runtime identity與預期不符。
- 三個Secret references缺失、version不符或任何runtime secret退回plain env。
- `WEB_PORTAL_ADMIN_MEMBER_IDS` absent或格式preflight／revision設定無法確認存在（不得顯示value）。
- Production demo gates被啟用，或`GET /demo/`不是404。
- `GET /`不是200、發生redirect loop或5xx。
- Temporary env file無法安全清除。
- 發現任何Secret／env value進入log、image context、Git或非預期輸出。

若build在Cloud Run mutation前失敗，沒有traffic需要rollback；停止並回報即可。

## 7. Rollback方法與驗證

精確rollback：

```text
gcloud run services update-traffic web-portal \
  --project=ntubtob-schedule-405614 \
  --region=asia-east1 \
  --to-revisions=web-portal-00026-rtc=100
```

Rollback後只驗證：

- `web-portal-00026-rtc` Ready且承接100% traffic。
- Public IAM／ingress不變。
- Service URL不變。
- 不重跑LINE Login或DB頁面。

Rollback會恢復舊revision與舊runtime設定；在新revision期間產生的新session cookie可能無法被舊Session Secret驗證。不得刪除新revision、image或Secret versions。

## 8. 明確不包含

- Secret payload readback、version新增／disable／destroy／delete或IAM修改。
- `WEB_PORTAL_ADMIN_MEMBER_IDS` value讀取、輸出、提交或修改。
- LINE Login、callback、profile或token exchange測試。
- Production DB、attendance、games、member matching讀寫或任何POST。
- LINE／Discord／email／push通知。
- Schema、migration、Supabase、Scheduler或其他服務部署。
- Production啟用demo mode。
- Merge、push或PR；deployment closeout預設只做local文件commit，另有授權除外。

## 9. 完成紀錄

產出`docs/operations/deployments/WEB_PORTAL_CDB67BF.md`，記錄：

- account／project／region／target
- build ID、approved commit、image tag／digest
- old／new revisions與traffic
- runtime key分類，不含values
- public／ingress／runtime identity
- HTTP `GET /`與`GET /demo/`狀態
- rollback是否觸發及結果
- 未驗證項目與已知風險

同步更新TASK、PROJECT_STATE、DECISIONS與HANDOFF並建立描述性local commit。

## 10. 需要Owner批准的精確文字

若Owner同意部署，請批准：

> 批准將commit `cdb67bf007ec67d882c6e974143a4d527f1528cd`依TASK-027部署至production `web-portal`，使用`web-portal-line-login-channel-secret:1`與`web-portal-session-secret-key:1`，並帶入我已在local正式env設定的`WEB_PORTAL_ADMIN_MEMBER_IDS`。我接受既有登入session失效。批准build、deploy、control-plane／metadata驗證、各一次無副作用`GET /`與`GET /demo/`，以及在TASK-027失敗條件下將100% traffic rollback至`web-portal-00026-rtc`。不批准Secret讀回／修改、IAM修改、LINE Login／DB／管理功能測試、通知、其他服務部署、schema／data操作、push、PR或merge。
