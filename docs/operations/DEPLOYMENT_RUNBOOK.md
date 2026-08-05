# Production Deployment Runbook

更新時間：2026-08-05
狀態：`accepted`
適用環境：Google Cloud production
預設 project／region：`ntubtob-schedule-405614`／`asia-east1`

## 1. 目的與授權邊界

本文件將現有手動部署整理為可重複、可查證、可停止及可 rollback 的受控流程。它不代表任何一次實際部署已獲批准。

Owner 於 2026-08-04 接受本文件作為標準流程。此接受僅採納文件與批准閘門，不授權任何一次實際部署、雲端變更、Secret 操作、正式通知或 production data 操作。

每次 production deployment 必須由 Owner 針對下列內容一次明確批准：

- 服務名稱與環境。
- 要部署的 Git commit。
- 使用的 deployment target。
- 預期外部副作用及驗證方式。
- rollback 目標。

在 Owner 批准前，只能執行 repository 內的離線測試與靜態檢查；不得執行 `make deploy-*`、`gcloud builds submit`、`gcloud functions deploy`、流量切換、Secret／IAM／Scheduler 修改或真實 LINE／Discord 測試。

## 2. 已確認部署拓撲

| 元件 | 平台 | Repository 入口 | 對外邊界 | 目前狀態 |
| --- | --- | --- | --- | --- |
| `web-portal` | Cloud Run | `make deploy-web-portal` | Public | Repository 邊界已由 TASK-022 強化；仍等待 production inventory、exact Secret references、IAM 驗證與 rollback 工作包。 |
| `game-broadcast-service` | Cloud Run | `make deploy-game-broadcast-service` | Private | Repository contract tests 已存在；尚未做線上整合驗證。 |
| `notify-cronjob-service` | Cloud Run | `make deploy-notify-cronjob-service` | Private | Repository contract tests 已存在；尚未做線上整合驗證。 |
| `update-game-schedule` | Cloud Functions Gen2 | `make deploy-update-game-schedule` | Private | Python 3.10；尚無完整 deployment contract／線上驗證。 |
| `line-webhook-handler` | Cloud Functions Gen2 | `make deploy-line-webhook-handler` | Public；應驗證 LINE signature | Python 3.10；尚無完整 deployment contract／線上驗證。 |

共同事實：

- Apps 透過 Cloud Build 建置 Docker image，再部署 Cloud Run。
- Apps 與 functions 都會先重建 `shared_lib-0.0.1.tar.gz`，並複製至 deployment source 的 `dist/`。
- 兩個 private scheduled services 與 Web Portal repository config 已使用完整 Git SHA 作 immutable image tag；仍必須記錄 Git SHA、build ID、image digest 與 revision。Web Portal 尚未完成 production readiness，維持禁止部署。
- Repository 沒有 migration framework；任何 schema 變更均不得附帶於一般部署。
- Repository 沒有 Cloud Scheduler job 定義；實際 jobs、OIDC service account 與 target URLs 尚待受控唯讀 inventory。

## 3. 目前禁止部署的情況

符合任一條件即停止：

- Git working tree 有無法解釋或不屬於部署內容的變更。
- 要部署的 commit 尚未 merge 至 `main`，或 CI 未成功。
- 涉及 database schema／migration，但沒有相容性、backup、回填與 rollback 計畫。
- 無法確認目前 gcloud account、project、region 或 target service。
- 無法確認必要 Secret version 已 enabled，或 runtime service account 具 accessor 權限。
- 會發送真實 LINE／Discord 訊息，但未取得該次通知的明確批准。
- 無法辨識前一個 healthy revision／commit，或沒有 rollback 路徑。
- Build context 可能包含 `.env.yaml`、credential 或其他 Secret。
- 部署會改變 public/private boundary、IAM、Scheduler、Secret 或流量策略，但本次授權未包含該項目。

### Web Portal deployment blockers

TASK-022 已建立 repository-only 防護：temporary runtime env 會過濾三項 Secret、Docker 排除該檔案、Cloud Run 設定三項 runtime Secret bindings，且 image tag 使用 exact Git commit。這些檢查不代表已批准或驗證 production deployment。

部署 `web-portal` 前仍必須提供 LINE Login 與 session Secret 的 exact resource references、在不讀取 Secret value 下確認 resource 與 runtime IAM、盤點目前 production revision 與 public boundary，並由 Owner 批准 exact rollback revision。此服務因產品需求維持 public。

## 4. 部署請求摘要

每次執行前先填寫並交 Owner 批准：

```text
Environment: production
Target service/function:
Git commit SHA:
PR / CI run:
Expected behavior change:
Database/schema impact: none / details
Secret/env impact: none / details
Authentication boundary: public / private / unchanged
Real notification risk: none / details
Pre-deploy healthy revision or prior commit:
Rollback method:
Post-deploy checks:
Requested execution window:
```

批准文字應明確到類似：

```text
批准將 <commit> 部署至 production 的 <service>，依 runbook 執行建置、部署、驗證與必要 rollback；不包含其他服務、Secret/IAM/Scheduler 修改或真實通知。
```

## 5. 部署前 repository 檢查

### 5.1 Git 與變更範圍

```text
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --format=fuller
git diff --check
```

必要結果：

- HEAD 是 Owner 批准的 commit，且已存在於 `origin/main`。
- 工作樹乾淨；若只有 Owner 明確保留的未追蹤資產，也不得讓它進入 build context。
- 實際 diff 不含非預期 schema、Secret、IAM、public access 或通知行為變更。

### 5.2 離線測試

```text
python -m unittest discover -s apps/game_broadcast_service/tests -v
python -m unittest discover -s apps/notify_cronjob_service/tests -v
python -m unittest discover -s functions/update_game_schedule/tests -v
```

並確認對應 PR 的 GitHub Actions 在 CPython 3.10 成功。測試成功只代表 repository 行為，不代表 GCP 整合成功。

### 5.3 gcloud 身分與目標

下列為部署核准後的唯讀 preflight；不得顯示 access token 或 Secret value：

```text
gcloud auth list
gcloud config get-value account
gcloud config get-value project
gcloud config get-value run/region
```

必要結果：

- account 是 Owner 預期的部署身分。
- project 精確等於 `ntubtob-schedule-405614`。
- region 明確為 `asia-east1`；若 config 未設定，部署命令仍必須顯式帶入。

### 5.4 捕捉 rollback 基準

部署前以唯讀方式記錄：

- 目前 serving revision／function update time。
- 目前 traffic allocation。
- 目前 image digest 或前一個已驗證 Git commit。
- Runtime service account。
- Public/private IAM 邊界。
- 必要 Secret 的「名稱、版本與 enabled 狀態」，不得讀取 value。
- Scheduler target 與 service 是否一致；此項需另取得雲端 inventory 授權。

輸出不得包含環境變數值、authorization header、LINE token、database password 或完整 request body。

## 6. Shared library 檢查

所有 deploy targets 都會重新 build shared library。部署前必須：

1. 確認 `shared_lib/shared_module/` 是否在目標 commit 中有變更。
2. 執行 `make build-shared-lib`。
3. 確認 `shared_lib/dist/shared_lib-0.0.1.tar.gz` 是本次剛產生，而不是舊 artifact。
4. 確認 target 的 `dist/` 收到同一份 artifact。
5. 若 shared library 有變更，驗證所有直接受影響服務；不得只測單一 caller。

目前 package version 固定為 `0.0.1`，因此不能用檔名判斷內容版本；必須以 Git SHA、檔案 hash、Cloud Build ID 與 image digest建立追溯紀錄。

## 7. 各服務執行入口與閘門

### 7.0 Scheduled services 的標準 wrapper

`game-broadcast-service` 與 `notify-cronjob-service` 的標準入口為：

```text
python tools/deploy_scheduled_service.py <SERVICE>
```

未帶 `--execute` 時只做 repository preflight，不執行 `gcloud` 或任何雲端查詢／變更。Windows 若沒有 `python` alias，使用：

```text
py -3.10 tools/deploy_scheduled_service.py <SERVICE>
```

Owner 完成單次 deployment work package 批准後，執行者才可使用：

```text
python tools/deploy_scheduled_service.py <SERVICE> --execute \
  --approved-commit <FULL_40_CHARACTER_SHA> \
  --rollback-revision <EXACT_PREVIOUS_HEALTHY_REVISION>
```

Wrapper 會 fail closed 檢查 clean source、HEAD、服務與 rollback revision，重建 shared sdist、過濾暫存 env、用批准 SHA 建置 image，確認新 revision ready，並明確將 100% traffic 指向新 revision。Cloud Build 成功不等於 rollout 成功；new revision／traffic 驗證失敗時會嘗試切回批准的 exact rollback revision。暫存 `.env.yaml` 會在成功或失敗時清理。

命令輸出只能記錄 build ID、revision、SHA tag 等非敏感識別資料。不得把 env value、Secret value、token 或完整 runtime configuration 寫入證據。舊 Make targets 保留相容性，但 production 優先使用 wrapper。

### 7.1 Game broadcast service

Legacy 入口：

```text
make deploy-game-broadcast-service
```

已確認設定：

- Cloud Run private：`--no-allow-unauthenticated`。
- Runtime Secret bindings：database password、weather API key、LINE channel access token。
- Temporary env file 會排除 LINE access token 與 channel secret。
- `.dockerignore` 排除 `.env.yaml` 與 tests。

額外閘門：部署成功後不可直接呼叫 invitation、cancellation 或 reminder endpoints 作 smoke test，因為它們可能發送真實 LINE／Discord 訊息或寫入資料庫。取得該次 production deployment 的明確授權後，可使用具 Cloud Run Invoker 權限的身分，以 identity token 呼叫 private `GET /healthz`；此路徑不讀取資料庫，也不呼叫 LINE、Discord 或 weather。它只能證明 container 中的 Flask process 與 route 正常，不能證明外部依賴健康。若部署授權未涵蓋 production endpoint invocation，仍只做 revision、startup logs、IAM 與 traffic 的唯讀 control-plane 驗證。

### 7.2 Notify cronjob service

Legacy 入口：

```text
make deploy-notify-cronjob-service
```

已確認設定：

- Cloud Run private：`--no-allow-unauthenticated`。
- Runtime Secret bindings：database password、LINE channel access token。
- Temporary env file會排除 LINE access token 與 channel secret。
- `.dockerignore` 排除 `.env.yaml` 與 local artifacts。

額外閘門：兩個 POST endpoints 會公告賽程或發送出席統計，未經獨立通知批准不得用正式 endpoint 做 smoke test。取得該次 production deployment 的明確授權後，可使用具 Cloud Run Invoker 權限的身分，以 identity token 呼叫 private `GET /healthz`；此路徑不讀取資料庫，也不呼叫 LINE、Discord、crawler 或 weather，且只能證明 Flask process 與 route 正常。若部署授權未涵蓋 production endpoint invocation，不得因 health route 無副作用而自行呼叫。

### 7.3 Web Portal

入口會在缺少必要 repository 參數時 fail closed，目前仍須 deployment work package 才可執行：

```text
make deploy-web-portal
```

必要參數為 40 字元 `IMAGE_TAG`、`WEB_PORTAL_LINE_LOGIN_SECRET_REF` 與 `WEB_PORTAL_SESSION_SECRET_REF`。後兩者只能是 Secret resource/version references，不得是 Secret values。正式工作包還必須確認 callback URL、public boundary、Secret IAM、目前 revision 與 rollback target。Repository contract tests 不會執行 Docker build、Cloud Build、Secret lookup 或 Cloud Run deployment。

### 7.4 Update game schedule function

入口：

```text
make deploy-update-game-schedule
```

已確認設定：Gen2、Python 3.10、HTTP trigger、private、database password Secret binding。

額外閘門：該 function 可能呼叫 crawler 並修改賽程資料；未經 production data 與 external-call 授權，不得以正式 invocation 做 smoke test。部署前應先補 deployment contract 或做人工靜態查驗，確認 `--no-allow-unauthenticated` 未退化。

### 7.5 LINE webhook handler

入口：

```text
make deploy-line-webhook-handler
```

已確認設定：Gen2、Python 3.10、HTTP trigger、public、database password 與 Web Portal URL Secret bindings。

額外閘門：Public 是 LINE webhook 所需邊界，但 application 必須持續驗證 LINE signature。部署前需確認 LINE credentials 的 runtime 傳遞方式及 source upload exclusions；不得用真實 LINE event 測試，除非 Owner 另行批准。

## 8. Temporary file 與失敗清理

三個 app Make targets 都在 Cloud Build 成功後才刪除 service directory 的 `.env.yaml`。若 legacy build/deploy 中途失敗，清理步驟可能不會執行。Scheduled services wrapper 則以 `finally` 保證暫存 env 清理。

無論成功或失敗都必須：

1. 確認 `apps/<target>/.env.yaml` 已移除。
2. 確認 `git status --short` 沒有意外 staging 或新 credential file。
3. 不讀取、不輸出、不複製該檔內容。
4. 若檔案仍存在，使用明確 target path 刪除；不得使用廣泛 recursive delete。

## 9. 部署中監控與停止條件

部署時記錄：

- 開始時間、操作者、target、commit SHA。
- Cloud Build ID 或 Functions operation ID。
- 新 image digest、新 revision／function update time。
- Build、push、deploy 每一步結果。

立即停止後續驗證／流量操作的情況：

- Build context 或 log 出現 Secret／個資。
- Service authentication boundary 與預期不同。
- 新 revision 無法 ready、反覆 crash、database connection error 或缺少必要 config。
- 意外觸發 LINE／Discord、crawler 或 production data write。
- 無法辨識新舊 revision 或 rollback target。

## 10. 部署後安全驗證

### 所有元件

- 確認 deployed revision/function 對應批准的 commit、build ID 與 image digest。
- 確認 service account、region、runtime、Secret bindings 名稱／版本及 public/private boundary 未退化。
- 檢查 startup 與近期 error logs；不得輸出 Secret、完整外部 response 或個資。
- 確認舊 healthy revision／prior commit 仍可用於 rollback。
- 確認 temporary `.env.yaml` 已清理。

### 無副作用 smoke checks

- Web Portal 完成 production inventory、Secret/IAM 驗證與 exact rollback 工作包前不部署。
- Private notification services 預設只驗證 revision ready、IAM 與 startup logs，不呼叫會發訊息的 POST routes。
- Update schedule 預設不 invoke，以免 crawler／DB 寫入。
- LINE webhook 預設不送真實 event；若未建立安全的 signed synthetic test，僅驗證部署狀態與 signature validation code未退化。

若無法執行行為 smoke test，交付時必須明說「部署完成但線上業務流程未驗證」，不得宣稱完整成功。

## 11. Rollback

### 11.1 Cloud Run apps

優先做流量 rollback，而不是重建舊 image：

1. 確認部署前已記錄的 previous healthy revision。
2. 將 100% traffic 切回該 revision。
3. 確認 traffic allocation、revision ready 與 error logs恢復。
4. 保留失敗 revision供調查，不立即刪除。

命令模板（執行前替換並再次確認 exact service/revision）：

```text
gcloud run services update-traffic <SERVICE> \
  --region asia-east1 \
  --project ntubtob-schedule-405614 \
  --to-revisions <PREVIOUS_HEALTHY_REVISION>=100
```

Scheduled services 的 image tag 必須等於批准的完整 Git SHA；既有 revision 仍以 image digest 固定。部署前必須驗證 previous revision 可用；若無 previous healthy revision，不得開始部署。

### 11.2 Cloud Functions Gen2

Repository 未提供自動 rollback target。預設方法是從已記錄的 previous healthy Git commit 重建 shared library並重新 deploy 同一 function：

1. 停止任何會重複觸發副作用的人工 invocation。
2. 確認 previous commit 與其 env/Secret contract。
3. 取得 Owner 對 rollback deploy 的確認；緊急 rollback 可包含在原部署授權，但 target 必須事先寫明。
4. 從 previous commit 執行對應 `make deploy-*`。
5. 重新確認 IAM boundary、runtime、entry point、logs 與 Scheduler target。

不得假設 Cloud Functions Gen2 的 underlying Cloud Run revision 可以直接作為受支援的 function rollback；除非已查證並寫入後續版本 runbook。

### 11.3 Data／notification rollback 限制

- Code rollback 不會撤回已發送的 LINE／Discord 訊息。
- Code rollback 不會自動還原已寫入的 database data。
- 若部署可能產生上述副作用，必須在執行前另有 idempotency、資料修復與溝通計畫。
- 未經 Owner 批准不得刪除或手動回寫 production data。

## 12. 部署結果紀錄

每次部署完成或 rollback 後保存：

```text
Result: success / partial / rolled_back / failed
Target:
Approved commit:
Actual build ID / operation ID:
Image digest / revision / function update time:
Previous healthy revision or commit:
Authentication boundary verified:
Secret bindings verified without reading values:
Smoke checks performed:
Checks intentionally not performed:
External notifications sent: no / approved details
Production data writes: no / approved details
Rollback performed:
Remaining risks:
```

部署紀錄應進入獨立 deployment report；不得把 Secret、token、完整環境變數或個資寫入 repository。

## 13. 待補強項目

### P1

- 完成 Web Portal production inventory、Secret/IAM 與 rollback readiness。
- 建立各 function deployment contract tests。
- 建立不會發通知／寫資料的 health check 或 safe smoke strategy。
- 取得 Cloud Run、Functions、Scheduler、service account、IAM、Secret version 的受控唯讀 inventory。

### P2

- 將 scheduled services wrapper 納入未來的 protected deployment environment；目前仍為 Owner 單次批准後的人工執行。
- 建立 staging 與 fake notification adapter。
- 將 production deployment 放入 GitHub protected environment，由 Owner 保留最終批准。
- 增加自動捕捉 previous healthy revision 與 rollback command 的工具。

### P3

- 補齊 migration、backup、restore 與 data rollback runbook。
- 統一服務 health、structured logging、request ID 與告警策略。

## 14. 已確認、推論與待確認

### 已確認

- Repository 的 deploy targets、project、region、runtime、公開／私有 flags 與上述 Secret binding 名稱。
- Web Portal 與兩個 scheduled services 的 repository config 均使用完整 Git SHA tag；尚未驗證 Web Portal production rollout。
- Web Portal build context 已有靜態 contract；Cloud Build 與 image 尚未實跑驗證。
- Repository 尚無 migration framework、Scheduler definitions 與無副作用 health endpoints。

### 推論

- Private services 應由 Cloud Scheduler 使用 OIDC／IAM 呼叫。
- 舊 Cloud Run revision通常可作 traffic rollback，但仍需每次部署前以實際服務狀態確認。

### 待確認

- 實際 gcloud deployment account、Cloud Build service account 與 runtime service accounts。
- Cloud Scheduler jobs、頻率、OIDC identities 與 target URLs。
- Secret versions enabled 狀態與 accessor IAM；不得讀取 values。
- Artifact Registry retention 與 previous revision/image 可用性。
- Cloud Run min/max instances、concurrency、timeout 與 traffic policy。
- LINE webhook／Login channel 與正式 callback 設定。
