# TASK-076 Codex report

## 任務狀態

- 狀態：`ready_for_review`
- Branch：`codex/phase-c-rollout-planning`
- Base commit：`893e36521396312e7dcc60b40e4433f9907087e2`
- Implementation head：`699259a5025eed27125b85d17a4fcf38f61564e2`
- PR：依 task 預設未建立；Work 驗收 shared branch 後建立唯一 ready PR

## 實作結果

- 在 shared runtime 建立 exact-`true`、demo-safe 的 Phase C／identity maintenance
  狀態機。缺少、空白、大小寫或其他值均為 off；maintenance-on／Phase-C-off
  為 invalid 且 effective maintenance off。
- Web Portal、LINE webhook 與 shared attendance analyzer 改用同一 Phase C
  runtime helper。Web Portal identity maintenance 不再能獨立於 Phase C 開啟。
- 建立三服務 rollout vector classifier。全 off、全 on／maintenance off、全
  on／maintenance on 是允許的穩定狀態；任何單一或兩服務組合均 fail closed。
- 補上 mixed-version attendance adapters：Phase C reader 可藉 Member→Person
  投影讀取 feature-off revision 新寫入的 Member reply；legacy reader 會忽略無
  fake Member 的 Phase C guest row，而不建立 invalid Member 或中斷整批讀取。
  這只保資料安全，不把 mixed mode 宣稱為正常流量相容。
- 新增 PostgreSQL 0004 跨服務 fixture，驗證 feature-off 零 identity side
  effect、Member pairing、team/guest eligibility、Portal/Webhook/notify projection、
  formal/display name、retry/double-click idempotency、revocation，以及
  disabled/blocked Person 不因登入或重試恢復。
- 新增 secret-free offline preflight，檢查 explicit rollout flags、三個 example
  env default-off、三份 requirements 的 exact sdist path、shared source與四份
  artifact內容一致，以及 Web/notify Docker與webhook gcloud build context排除
  env、credential、private backup/local DB及無關 dist。
- 新增分階段 feature-off deployment、coordinated activation、maintenance final
  stage、15/30分鐘觀察／停止條件及兩層 rollback runbook。明確指出repository
  沒有原子跨服務env update；TASK-077若無法建立attendance/notification freeze，
  activation必須 blocked。
- CI的既有PostgreSQL formatting gate納入本次Python files；未降低或移除任何
  existing test、main safety net、authentication、authorization或signature boundary。

## Caller與artifact結論

- Direct callers：Web Portal、LINE webhook、notify cron（經shared attendance
  analyzer）與shared library。
- `game_broadcast_service`不是Phase C direct caller，不讀這兩個flags或lifecycle
  repository，因此未納入後續Phase C部署單元；仍執行完整28項回歸確認無影響。
- Web Portal、LINE webhook與notify cron都必須取得由同一current source建立的
  `shared_lib-0.0.1.tar.gz`。本機最終preflight確認三份target artifact與source一致。

## 變更檔案

主要程式與測試：

- `shared_lib/shared_module/portal_data/runtime.py`
- `shared_lib/shared_module/portal_data/identity_lifecycle.py`
- `shared_lib/shared_module/attendance_analyzer.py`
- `apps/web_portal/app.py`
- `apps/web_portal/identity_maintenance.py`
- `functions/line_webhook_handler/webhook.py`
- `tests/portal_data/test_phase_c_rollout_state.py`
- `tests/portal_data/test_phase_c_cross_service_rollout.py`
- `tests/portal_data/test_phase_c_attendance_analyzer.py`
- `apps/web_portal/tests/test_admin_security.py`
- `functions/line_webhook_handler/tests/test_attendance_reply.py`

Preflight、CI與build contexts：

- `tools/phase_c_rollout_preflight.py`
- `tools/tests/test_deploy_phase_c_rollout.py`
- `.github/workflows/python-tests.yml`
- `apps/web_portal/.dockerignore`
- `apps/notify_cronjob_service/.dockerignore`
- `functions/line_webhook_handler/.gcloudignore`

文件：

- `docs/operations/data/PORTAL_DATA_PHASE_C_APPLICATION_ROLLOUT.md`
- `apps/web_portal/README.md`
- `apps/notify_cronjob_service/README.md`
- `functions/line_webhook_handler/README.md`
- `shared_lib/README.md`
- Work建立、Codex完整承接的`docs/coordination/tasks/TASK-076.md`
- `docs/coordination/HANDOFF.yaml`（只做接手與completion handoff更新）

## 實際驗證

- Bundled Python：3.12.13；程式維持Python 3.10語法，最終hosted Python 3.10由
  Work建立的唯一ready PR補證據。
- Local PostgreSQL：`postgres:16.4-alpine`，task-owned Compose project
  `ntubtob-task076`，只綁`127.0.0.1:55432`與明顯假credential。
- `python -m unittest discover -s tests/portal_data -q`：170/170 passed，包含新增
  5項0004 cross-service PostgreSQL tests與7項flag/rollout state tests。
- `python -m unittest discover -s apps/web_portal/tests -q`：Ran 120，118 passed、
  2個Windows無`make/sh` platform skips。
- LINE webhook：19/19 passed；500負向案例的Flask error log是預期輸出，assertion通過。
- Notify cron：9/9 passed。
- Game broadcast：28/28 passed。
- Update game schedule：5/5 passed。
- `python -m unittest discover -s tools/tests -q`：67/67 passed。
- Phase C migration、evidence、readiness三個repository verifier：passed。
- `python -m compileall -q ...`：passed。
- Black 24.4.2（13個受影響Python files）：passed；isort `--profile black
  --check-only`：passed。
- Shared library sdist已由最終source重建、以`--no-deps --no-build-isolation`
  安裝到bundled runtime並複製至三個deployment units；沒有publish或upload。
- Offline rollout preflight的`legacy`、`phase_c`、`phase_c_maintenance`三個合法
  vector均passed，最終source fingerprint為
  `7ac895bafecde2ab259068da4bca3bc9ce605f2de20b3b9e1a2a9180fb86b78c`。
- `git diff --check`及staged diff check：passed。
- task-owned container、network與fake-data volume已`down -v`移除。

## 測試過程中的已處理事項

- 初次命令因Windows沒有global `python`而未啟動；依repository規範改用bundled
  Python，未修改Makefile或產品程式規避。
- 初次完整Web/Webhook回歸暴露installed sdist仍是舊版，以及Webhook test runtime
  stub缺新helper。重建／安裝current sdist並補齊fake-only stub後，完整suites通過。
- Preflight測試先發現notify `.dockerignore`少`.env*`，補齊後build-context gate通過。
  上述均在最終完整重跑前解決，沒有隱藏既存或最終失敗。

## 未執行與剩餘風險

- 未執行hosted Python 3.10/YAML parser、Cloud Build、Docker image build或任何
  GCP deploy；Work的唯一ready PR仍須通過change-aware final hosted CI。
- 未在production觀察三個runtime的實際env metadata、artifact image digest、revision、
  IAM、traffic或health。Local success不能證明production integration。
- Repository沒有atomic multi-service flag mutation。Normal traffic下的mixed mode仍
  明確禁止；TASK-077必須定義並由Owner批准exact freeze與external coordination，
  否則不得activation。
- 未做production smoke、登入、LINE postback、notify route invoke或identity mutation。
  後續若需要，必須鎖定虛構／安全測試身分、停止條件與獨立Owner批准。
- 本任務未新增或修改schema/migration SQL、正式runtime flag值、Secret、IAM、
  Scheduler、cloud resource或repository settings。
- 沒有production/Supabase連線、DDL/DML、deployment或真實LINE/Discord通知。

## Owner決策

本輪repository交付不需要新產品規則。TASK-077仍需Owner明確批准exact deployment、
flag mutation、attendance/notification freeze、任何production smoke及rollback traffic
mutation；若無可驗證freeze機制，Phase C activation應停止而非接受mixed mode。

## Git狀態

- Implementation commit：`699259a5025eed27125b85d17a4fcf38f61564e2`
- Completion report／handoff將建立一次描述性commit並push同一branch。
- Completion commit後預期無未提交修改；不建立Draft或ready PR。
