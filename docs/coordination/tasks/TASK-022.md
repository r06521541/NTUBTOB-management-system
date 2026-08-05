# TASK-022：強化 Web Portal Secret 與 Build Context 邊界

狀態：`ready_for_codex`
優先級：P1
規劃者：Work
執行者：Codex
Base commit：`a7f801b44e07d1d8518b9f8675e99b4743a98e00`

## 1. 任務目標

修正Web Portal目前會把完整`.env.yaml`送入Cloud Build並複製進container image的Secret外洩風險，將DB password、LINE Login channel secret與Flask session key改為Cloud Run runtime Secret references，並讓Web Portal image使用Git SHA不可變tag。

此任務只修改repository、建立離線deployment contract tests與Draft PR證據；不得執行Cloud Build、部署、讀取或操作Secret Manager、查詢production、發送通知或接觸production DB。

## 2. 已確認問題

- `deploy-web-portal`目前把`envs/web_portal/.env.yaml`完整複製到`apps/web_portal/.env.yaml`。
- Web Portal沒有`.dockerignore`，Dockerfile的`COPY . .`會把該檔案複製進image layer。
- `cloudbuild.yaml`目前只以runtime Secret綁定`DSN_PASSWORD`；`LINE_LOGIN_CHANNEL_SECRET`與`SECRET_KEY`仍可能來自env file。
- Web Portal Cloud Build與deploy仍使用固定`:tag1`，無法從commit追溯image／revision，亦可能產生deploy no-op。
- Web Portal必須保持public供LINE Login與使用者瀏覽；不能照private排程服務套用`--no-allow-unauthenticated`。
- 正式LINE Login secret與session secret的Secret Manager資源名稱尚未從repository確認，不得猜測或硬編碼。

## 3. 使用者價值

- LINE Login secret、session signing key與DB password不進入Docker image。
- Cloud Build source只可包含經過明確過濾的非機密runtime設定，不包含三項Secret值。
- Secret資源名稱未明確提供時部署流程fail closed，不會默默以env file fallback。
- Git commit、image tag與Cloud Run revision具備可追溯性，避免固定tag造成部署no-op。
- 為後續安全部署TASK-021管理端點保護建立必要前提。

## 4. 工作範圍

### 4.1 Build context排除

- 新增`apps/web_portal/.dockerignore`，至少排除：
  - `.env.yaml`與其他明顯env／credential檔。
  - Python cache、tests、coverage、virtualenv與不必要local artifacts。
- 必須保留Dockerfile實際需要的`requirements.txt`、application source、static/templates及精確shared library artifact。
- 若新增`.gcloudignore`，不得讓deploy依賴的過濾後runtime env消失；必須以contract test證明source與Docker兩層的安全語意，不可只靠檔名存在。

### 4.2 非機密runtime env

- `deploy-web-portal`不得再`cp`完整env file；改為明確排除至少：
  - `DSN_PASSWORD`
  - `LINE_LOGIN_CHANNEL_SECRET`
  - `SECRET_KEY`
- 過濾必須辨識key前置空白，並沿用scheduled services已驗證的安全模式。
- 過濾後檔案仍可包含Web Portal運行所需的非機密設定，包括`WEB_PORTAL_ADMIN_MEMBER_IDS`；本任務不得填入真實Member IDs。
- Build／deploy成功或失敗後都應清理temporary env；離線contract至少驗證command不會把Secret key從原env直接帶入image設定。

### 4.3 Runtime Secret references

- Cloud Run deploy必須以`--update-secrets`綁定：
  - `DSN_PASSWORD`
  - `LINE_LOGIN_CHANNEL_SECRET`
  - `SECRET_KEY`
- 既有DB Secret reference可維持目前已確認的`supabase-database-password:latest`。
- LINE Login與session Secret資源reference必須由明確的Cloud Build／Make substitution或參數提供；repository找不到正式資源名稱時不得自行假設、建立或硬編碼。
- 缺少、空白或placeholder Secret reference時，repository deployment entry point必須在Cloud Build／deploy前fail closed並提供不含Secret value的錯誤。
- 不綁定`LINE_LOGIN_CHANNEL_ID`為Secret；它可維持非機密runtime config。

### 4.4 Immutable image tag

- Web Portal Docker build、push與Cloud Run deploy使用同一`${_IMAGE_TAG}`，不得使用`:tag1`、`:latest`或可變fallback。
- Make target從exact Git commit傳入`_IMAGE_TAG="${IMAGE_TAG}"`，與scheduled services現有規則一致。
- 本任務不擴張`tools/deploy_scheduled_service.py`支援Web Portal；公開服務的驗證與rollback另立deployment readiness任務。

### 4.5 Public boundary與demo安全

- Web Portal維持`--allow-unauthenticated`，因LINE Login callback與公開頁面需要外部流量。
- 不得在production部署設定開啟`WEB_PORTAL_DEMO_MODE=true`或`WEB_PORTAL_ENV=development`。
- 不修改LINE Login、管理authorization、CSRF、session行為或UI。

### 4.6 Deployment contract tests與CI

- 在`apps/web_portal/tests/`新增離線deployment contract tests，至少驗證：
  - `.dockerignore`排除`.env.yaml`、cache、tests與local artifacts，同時未排除必要shared artifact。
  - Make target不再完整copy env，會排除三個Secret keys並支援前置空白。
  - Cloud Run deploy綁定三個runtime Secret variables。
  - 未知的LINE Login／session Secret resource以必填參數傳入，而非硬編碼猜測或Secret value。
  - Docker build、push、deploy與Make substitution均使用同一immutable Git SHA tag，且不存在`:tag1`／`:latest`。
  - Web Portal仍public，且production config沒有開啟demo gates。
- 加入mutation-style assertions或fixture，使移除ignore、Secret filter、Secret binding、immutable tag或public boundary時測試會失敗。
- 現有Python 3.10 CI已執行完整Web Portal tests；不得加入GCP credential、write permission、build、deploy或外部請求。

### 4.7 文件

- 更新`apps/web_portal/README.md`，說明repository-only preflight、必填Secret resource references、非機密admin allowlist與禁止直接deploy的界線。
- 更新`docs/operations/DEPLOYMENT_RUNBOOK.md`的Web Portal禁止部署原因：TASK-022合併後可改為「等待production inventory、exact Secret references與rollback工作包」，但不得宣稱已可部署或已驗證Secret IAM。
- Codex完成後更新report；Work驗收後更新review、`PROJECT_STATE.md`與`HANDOFF.yaml`。

## 5. 非目標

- 不執行`gcloud builds submit`、Cloud Run deploy、traffic切換或production request。
- 不讀取、列出、建立、修改、輪替或刪除Secret Manager資源／version／value，不查IAM。
- 不讀取或顯示`envs/**/.env.yaml`或服務目錄內真實`.env.yaml`。
- 不填入真實Member IDs、LINE channel資料、DB user／host或session secret。
- 不部署TASK-021，不設定production `WEB_PORTAL_ADMIN_MEMBER_IDS`。
- 不修改schema、shared library、LINE Login／session／authorization業務程式或其他服務deployment config。
- 不建立Web Portal完整deployment wrapper；留給下一個production readiness任務。

## 6. 設計決策

- Secret值只在Cloud Run runtime由Secret Manager注入；Cloud Build substitutions只傳Secret resource reference，不傳Secret value。
- 未確認的Secret resource名稱採必填參數，不在repository以看似合理的名稱猜測。
- 過濾後的非機密env file可以進入Cloud Build source供`gcloud run deploy --env-vars-file`使用，但`.dockerignore`必須阻止其進入image。
- Public Cloud Run boundary是Web Portal既有產品需求；安全性由LINE OAuth、session及route authorization提供，不把整個服務改private。
- Immutable tag使用40位Git commit SHA；實際production rollout／digest／revision驗證另立精確工作包。

## 7. 驗收條件

- 完整env file不再被copy到Web Portal build source；temporary env明確排除三項Secret key。
- `.env.yaml`不進Docker image context，必要shared artifact仍可build。
- 三項Secret均由runtime binding取得，未知resource reference未提供時fail closed。
- Web Portal build／push／deploy使用同一Git SHA tag，無`:tag1`或`:latest`。
- Web Portal維持public，demo production gates維持關閉。
- Deployment contract tests與現有Web Portal／全repository離線回歸均通過；Python 3.10 CI成功。
- `git diff --check`及設定靜態檢查通過。
- 文件明確說明尚未build、deploy、驗證Secret存在性／IAM或production runtime。

## 8. 驗證命令

```powershell
python -m unittest discover -s apps/web_portal/tests -v
python -m unittest discover -s functions/line_webhook_handler/tests -v
python -m unittest discover -s apps/game_broadcast_service/tests -v
python -m unittest discover -s apps/notify_cronjob_service/tests -v
python -m unittest discover -s functions/update_game_schedule/tests -v
python -m unittest discover -s tools/tests -v
git diff --check
git status --short
```

Docker／Cloud Build／gcloud只做靜態contract驗證；本任務不得實際build或deploy。

## 9. 影響範圍與依賴

- 預估檔案：Web Portal `.dockerignore`、`cloudbuild.yaml`、`makes/deploy_apps.mk`、deployment contract tests、README、runbook及CI（若現有discover不需改則不必修改）。
- 不修改application runtime code、schema或dependencies。
- 主要依賴：Owner未來須提供或批准LINE Login與session Secret的exact resource references；本任務只建立fail-closed參數邊界。

## 10. PR 工作包（Owner 已批准）

Owner已批准Codex：

- 建立`codex/harden-web-portal-build-boundary` branch。
- 建立描述性local commits、push並建立Draft PR。
- 執行離線測試與GitHub Actions，於同一PR更新Codex report及交棒文件。

仍不包含ready／merge、Docker／Cloud Build實跑、deployment、production request、正式通知、production DB、Secret／IAM／Scheduler、schema或其他雲端操作；merge須由Owner在Work驗收後另行批准。
