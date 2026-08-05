# TASK-019：建立Immutable Image與跨平台Deployment Wrapper

狀態：`ready_for_codex`
優先級：P1
規劃者：Work
執行者：Codex
Base commit：`b14dcad3d1261772c8dc00898ba1caca114ce941`

## 1. 任務目標

消除`game-broadcast-service`與`notify-cronjob-service`固定使用`:tag1`造成的Cloud Run deployment no-op與追溯風險，並提供Python 3.10標準函式庫實作的跨平台deployment wrapper，讓Windows不依賴`make`、`grep`、`cp`或`rm`也能執行一致的安全preflight與已批准deployment流程。

此任務只修改repository並做離線驗證；不得實際呼叫`gcloud builds submit`、部署、切traffic、讀取production、發送通知或操作雲端資源。

## 2. 背景與已確認問題

- 三個Cloud Run app的Cloud Build目前使用固定`:tag1`。
- TASK-018新image已push至新digest，但Cloud Run template仍是相同`:tag1`字串，原deploy step沒有建立新revision。
- TASK-014 rollback後traffic明確pin在舊revision；即使建立new revision，也可能維持0% traffic，必須先驗證再顯式切換。
- Windows環境沒有`make`；目前須手動等價執行shared artifact、env filtering、Cloud Build與cleanup。
- 預設Python環境可能沒有Flask，但deployment wrapper本身可限制使用Python 3.10標準函式庫，不依賴application packages。
- `gh.exe`與`gcloud.cmd`可能未加入PATH；wrapper應提供清楚的missing-tool錯誤，不硬編碼使用者路徑。

## 3. 使用者價值

- 每次image都有Git SHA-based immutable tag，可建立commit→build→digest→revision追溯。
- Windows與Unix-like環境使用同一套安全檢查與執行語意。
- Deployment預設fail closed，未帶明確execute與批准參數時不得產生雲端mutation。
- 敏感env排除與temporary file cleanup不再依賴人工workaround。
- 能辨識Cloud Run traffic被pin在舊revision的情況，避免「build成功」被誤判為「新版已上線」。

## 4. 工作範圍

### 4.1 Immutable image references

- 修改兩個scheduled services的`cloudbuild.yaml`，新增必要的`_IMAGE_TAG` substitution。
- Docker build、push與Cloud Run deploy必須使用同一個非`latest`、非`tag1`的image tag。
- Make targets必須從當前exact Git commit產生合法且可追溯的tag並傳入Cloud Build。
- 不修改Web Portal Cloud Build；其deployment仍被runbook禁止，避免在同一任務混入Secret boundary工作。

### 4.2 Cross-platform wrapper

- 新增例如`tools/deploy_scheduled_service.py`的Python 3.10-compatible CLI，只支援：
  - `game-broadcast-service`
  - `notify-cronjob-service`
- 預設只做offline／read-only preflight；只有顯式`--execute`且提供exact approved commit與rollback revision時，才允許進入mutation path。
- 執行前至少驗證：repository root、clean deployment source、HEAD等於approved commit、commit可追溯、必要工具存在、env source存在、target service白名單、temporary env不存在。
- 使用標準函式庫重建shared sdist、複製artifact、產生filtered temporary env，並在`finally`保證cleanup。
- Game broadcast必須排除`CHANNEL_ACCESS_TOKEN`、`CHANNEL_SECRET`與`WEATHER_API_KEY`；notify cron必須排除LINE credentials。不得輸出env內容或Secret value。
- Cloud Build substitution必須帶入Git SHA image tag；wrapper須記錄build ID並取得built digest。
- Wrapper須以new revision／digest驗證實際rollout，不得只依Cloud Build `SUCCESS`宣稱部署成功。
- 若traffic仍pin在舊revision，wrapper應先驗證new revision與contract，再依已批准參數顯式切traffic；失敗時只能使用傳入的exact rollback revision。
- 所有外部command使用argument list，不以shell字串拼接token、path或Secret。

### 4.3 Documentation

- README記錄Windows與Unix-like的preflight用法，以及execute需要Owner精確批准。
- Deployment runbook更新immutable tag、pinned traffic與wrapper流程；保留人工批准閘門。
- 清楚說明wrapper存在不等於任何deployment已獲批准。

## 5. 非目標

- 不實際部署、build production image、切traffic或呼叫production endpoint。
- 不讀取真實`.env.yaml`內容；測試只使用明顯虛構env fixture。
- 不修改Web Portal、Cloud Functions、shared library source、schema、Secret、IAM或Scheduler。
- 不解決TASK-014的health URL／frontend 404。
- 不新增第三方Python dependency或PowerShell/Pester需求。
- 不建立自動部署CI/CD，不讓GitHub Actions持有production credential。

## 6. 測試要求

- 新增Python 3.10離線unit tests，以temporary repository／fake subprocess runner驗證：
  - 預設模式不呼叫mutation commands。
  - 缺少`--execute`、approved commit、rollback revision或工具時fail closed。
  - HEAD mismatch、dirty source、未知service、existing temporary env時停止。
  - Image tag由approved Git SHA產生，且Cloud Build／Cloud Run使用同一tag／digest。
  - 兩個service的敏感key均被排除，非敏感設定保留，輸出不含fixture secret values。
  - 成功、build failure、revision failure與traffic failure均清理temporary env。
  - Pinned traffic情境不會誤報成功；只有new revision驗證通過才允許traffic command。
  - Rollback command只能指向exact approved rollback revision。
- 更新既有deployment contract tests，禁止scheduled services再使用`:tag1`，並要求`_IMAGE_TAG`傳遞與weather key過濾。
- GitHub Actions加入wrapper tests；維持Python 3.10、read-only permissions且不執行外部請求。

## 7. 驗收條件

- Windows不安裝`make`也能執行一條文件化的preflight命令。
- Preflight不需要production credential也能完成repository／artifact／env fixture驗證；若要求雲端唯讀資料但無gcloud，提供清楚錯誤。
- Scheduled services不再以固定`:tag1`作為build／push／deploy identity。
- Wrapper預設無mutation，production execution需要明確雙重gate與exact values。
- 任一失敗路徑不遺留temporary `.env.yaml`。
- Web Portal仍明確blocked且不受本任務改動。
- Python 3.10 CI、game broadcast、notify cron、wrapper tests、compile與`git diff --check`通過。

## 8. 建議驗證命令

```text
python -m unittest discover -s tools/tests -v
python -m unittest discover -s apps/game_broadcast_service/tests -v
python -m unittest discover -s apps/notify_cronjob_service/tests -v
python -m compileall -q tools apps/game_broadcast_service apps/notify_cronjob_service
git diff --check
```

## 9. PR工作包建議

若Owner批准TASK-019與PR工作包，允許Codex建立／使用task branch、建立描述性commits、push、開Draft PR、查驗CI，以及由Work在同一PR更新report／review／PROJECT_STATE／HANDOFF。不得merge或執行wrapper的`--execute` path，除非Owner另行批准。

Owner已於2026-08-05批准TASK-019與上述PR工作包。
