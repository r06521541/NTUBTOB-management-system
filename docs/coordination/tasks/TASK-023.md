# TASK-023：Web Portal Production Deployment Readiness盤點

狀態：`awaiting_owner_decision`
優先級：P1
規劃者／執行者：Work（待Owner批准唯讀production盤點）
Base commit：`f7471da1fed20f6477a16d125a6347692e3e732d`

## 1. 任務目標

以嚴格唯讀、欄位最小化的GCP查詢，確認production `web-portal`目前的revision、traffic、image digest、public boundary、runtime identity、環境變數key與Secret reference metadata，辨識TASK-022所需的LINE Login／session Secret resource references與可用rollback revision，最後產出一份尚未執行的精確deployment工作包供Owner另行批准。

本任務不執行build、deploy、traffic切換、production HTTP request、Secret value讀取、IAM／Secret修改或production DB操作。

## 2. 背景與已確認事實

- TASK-021管理端點authorization／CSRF已合併但尚未部署。
- TASK-022 Web Portal Docker env排除、三項runtime Secret binding、immutable image tag與fail-closed preflight已合併但未build／deploy。
- 2026-08-04舊inventory顯示production `web-portal-00026-rtc`承接100% traffic、service public；LINE Login secret與Flask session key當時是plain runtime env而非Secret references。
- 舊inventory記錄default Compute Engine service account具project-level`roles/secretmanager.secretAccessor`，但目前狀態與最小權限仍需重新確認。
- Repository不知道LINE Login channel secret與session secret的正式Secret resource名稱；TASK-022禁止猜測。
- `WEB_PORTAL_ADMIN_MEMBER_IDS`尚未設定production；本任務不得讀取或記錄其實際value。
- Web Portal程式中的LINE callback URI是硬編碼URL；必須與目前Cloud Run service URL做唯讀比對，但本任務不查LINE Console或修改callback。

## 3. 使用者價值

- 在部署前知道目前真正服務中的revision與可rollback基準。
- 不讀取Secret value也能確認需要哪些Secret resources／versions與runtime accessor能力。
- 避免部署後才發現callback URL、public IAM、admin allowlist或runtime identity不相容。
- 將下一次Owner批准縮小為exact commit、exact target、exact Secret references與exact rollback revision。

## 4. 授權後可執行的唯讀查詢白名單

所有查詢限定project `ntubtob-schedule-405614`、region `asia-east1`與target `web-portal`；命令必須使用field-specific `--format`，不得輸出完整resource JSON／YAML。

### 4.1 操作者與target

- `gcloud auth list`只確認active account識別，不輸出token。
- `gcloud config get-value account`、`project`與`run/region`。
- 若project／region不符合，立即停止，不自動修改config。

### 4.2 Cloud Run control plane

- Service名稱、URL、latest created／ready revision、runtime service account、ingress、generation與update timestamp。
- Traffic revision與百分比，只保留target service資料。
- Current serving revision的Ready condition、image reference／digest、create time與service account。
- `roles/run.invoker`是否包含`allUsers`，只回報public true／false與必要role判定，不輸出完整IAM members清單。
- 不呼叫service URL，不讀request／application logs。

### 4.3 Runtime env key與Secret reference metadata

- Current service／revision只列env variable **名稱**，禁止輸出任何plain env value。
- Secret-backed env只列variable name、Secret resource name／version reference，不讀value。
- 特別判定下列keys存在方式：
  - `DSN_PASSWORD`
  - `LINE_LOGIN_CHANNEL_SECRET`
  - `SECRET_KEY`
  - `WEB_PORTAL_ADMIN_MEMBER_IDS`
  - `LINE_LOGIN_CHANNEL_ID`
- 對plain-value keys只記錄`plain／secret-backed／absent`，不得顯示值。

### 4.4 Secret與IAM metadata

- 若service metadata無法提供兩個新Secret resource名稱，可唯讀列出本project Secret **resource names**與labels以辨識候選；不得存檔或把無關完整清單寫入report。
- 未經Owner在看到候選後確認，不得自行把名稱相似的Secret認定為正式LINE Login／session Secret。
- 對Owner確認的exact Secret resources，只查version名稱／number、state、create time；不得執行`versions access`或任何payload操作。
- 只確認runtime service account是否具有`roles/secretmanager.secretAccessor`的有效binding；不輸出完整project IAM policy或無關members。
- 不建立Secret、不新增version、不enable／disable、不修改IAM。

### 4.5 Artifact與rollback metadata

- 確認current serving revision Ready且其image digest仍存在於revision metadata。
- 記錄可供rollback的exact revision、image digest與目前traffic；不得切traffic或下載image。
- 若current revision非100%、非Ready或digest缺失，標為deployment blocker並停止產生可執行批准文字。

## 5. 安全輸出規則

- 禁止輸出：Secret value、plain env value、access token、authorization header、cookie、LINE user ID、Member ID allowlist value、DB hostname／username／password或完整resource dump。
- Cloud Run URL、revision、digest、service account、Secret resource名稱／version metadata可作deployment證據，但只保留任務相關欄位。
- 若任何工具意外回傳可能的Secret或plain env value，停止，不將輸出複製到對話或repository；只回報查詢格式不安全並改用更窄field selector。
- 不讀`envs/**/.env.yaml`或service directory `.env.yaml`。

## 6. 工作範圍

- 執行上述唯讀inventory。
- 比對目前service URL與repository硬編碼LINE callback URL，只判定一致／不一致，不呼叫URL。
- 產出`docs/operations/deployments/WEB_PORTAL_READINESS_<DATE>.md`，明確區分已確認、推論、待Owner確認與blockers。
- 若資訊充分，草擬下一個exact deployment task，包含：
  - target `web-portal`
  - candidate commit（必須已在`origin/main`且CI成功）
  - two exact Secret resource/version references
  - non-secret `WEB_PORTAL_ADMIN_MEMBER_IDS`設定前置條件，但不記錄value
  - public boundary
  - previous healthy rollback revision
  - build／rollout／control-plane驗證與停止條件
  - 不含HTTP smoke、LINE Login、production DB或通知測試，除非Owner另批
- 本任務只產出readiness結果與下一步批准草稿，不執行deployment。

## 7. 非目標

- 不執行Docker、Cloud Build、`make deploy-web-portal`或Cloud Run mutation。
- 不建立、修改、輪替、刪除或存取Secret value。
- 不修改IAM、Cloud Run service、traffic、env、callback URL或admin allowlist。
- 不呼叫production Web Portal，不進行LINE Login或管理頁smoke test。
- 不連production DB、不查Member ID、不寫任何資料。
- 不修改程式碼、schema、migration、Scheduler或其他服務。
- 不自行認定名稱相似的Secret就是正確resource；歧義交回Owner。

## 8. 驗收條件

- Account／project／region與target經唯讀確認且符合預期。
- Current revision、traffic、digest、runtime identity與public boundary有欄位最小化證據。
- 五個關鍵env keys只以`plain／secret-backed／absent`分類，沒有value外洩。
- Secret resource／version metadata與runtime accessor只在Owner批准範圍查驗，沒有payload存取。
- Callback URL比對結果、rollback candidate與所有deployment blockers明確記錄。
- 產出下一次deployment所需決策清單與精確批准文字草稿；不得宣稱已部署或已驗證業務流程。
- `git diff --check`通過，working tree只含本次文件。

## 9. 停止條件

- Active account、project、region或service不符合。
- 查詢格式可能輸出Secret／plain env value。
- 找不到或無法唯一辨識LINE Login／session Secret resource。
- Runtime identity沒有可確認的Secret accessor。
- Current serving revision非Ready、traffic不明或沒有rollback digest。
- 任何步驟需要mutation、HTTP request、Secret payload、production DB或Owner未批准的擴張。

## 10. 需要Owner批准的精確範圍

若Owner接受TASK-023，批准內容僅包括第4節列出的production唯讀GCP metadata查詢，以及第6節readiness／deployment草稿文件更新與local commit。

不包含push／PR（此任務原則上可作為純inventory文件commit）、build、deploy、traffic、Cloud Run／IAM／Secret修改、Secret payload、production request、LINE Login、通知、production DB、schema或其他服務。
