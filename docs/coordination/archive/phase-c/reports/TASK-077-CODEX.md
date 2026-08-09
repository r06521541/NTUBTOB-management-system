# TASK-077 Codex report

## 狀態

- 狀態：`ready_for_review`
- Branch：`codex/phase-c-activation-freeze`
- Base commit：`43eb67c7f271ca29705a18c7133bdad51f7de29c`
- Implementation commit：`d02e0a31e2ac44491fa81bc9d07db38f511a7099`
- PR：未建立；依協作流程由 Work 驗收後建立唯一 ready PR。

## 完成內容

- 在 shared runtime 新增 exact-`true`、demo-safe 的
  `PORTAL_DATA_ROLLOUT_FREEZE_ENABLED`，並加入完整 Phase C／freeze／maintenance
  state classifier。mixed Phase C 只有在三個服務全部 frozen 時才是安全狀態。
- LINE webhook 在 signature dispatch 後、postback query parsing 與任何 principal、
  game、attendance、audit、Discord 存取前攔截 attendance reply；只用原 reply token
  回覆固定訊息，不 push／broadcast。
- notify cron 的 attendance-count POST 在 freeze 時回傳固定成功分類，且不查 DB、
  不執行 analyzer、不呼叫 LINE／Discord；health 與非 attendance route 不受影響。
- Web Portal 保留 OAuth state/session nonce、member/admin、authorization 與 CSRF guard
  的優先順序，再於 Phase C callback 及 identity/profile/member mutation 前回傳固定
  503；demo mode 永不啟用 production freeze。
- 新增純離線 transition controller：一次只規劃一個 canonical flag mutation，支援
  forward／rollback、commit 與 artifact fingerprint lock、固定 bounded human/JSON
  output；不執行 shell、HTTP、gcloud、Scheduler 或 DB。
- preflight、三個 env example、deployment wrapper contract、change classifier、服務
  README 與 Phase C runbook 已同步。TASK-078／079 所需證據與 Owner approval 邊界已
  明列；本任務未改正式 runtime flag 或 cloud resource。
- 依 Work 指示，在 `AGENTS.md` 加入 bundled Windows Python 的 Black CLI 停滯
  處理方式；兩個既有舊風格檔案只保留必要 freeze diff，未整檔格式化。

## 驗證結果

- `python -m unittest discover -s apps/web_portal/tests -q`：
  124 passed，2 個 Windows 缺少 `make`／`sh` 的既有 platform skips。
- `python -m unittest discover -s functions/line_webhook_handler/tests -q`：
  21 passed；輸出的 Flask traceback 是既有 dispatch-failure 負向測試預期 log。
- `python -m unittest discover -s apps/notify_cronjob_service/tests -q`：
  11 passed。
- `python -m unittest discover -s tools/tests -q`：88 passed。
- `python -m unittest tests.portal_data.test_phase_c_rollout_state -q`：
  11 passed。
- `python -m unittest discover -s tests/portal_data -v`：
  174 passed，61 skipped；skips 全為未提供隔離本機 PostgreSQL URL 的既有
  PostgreSQL tests。本任務不改 schema／migration／model／SQL，且 classifier
  contract 明定此 rollout-only 範圍不因 Phase C 名稱要求 DB matrix。
- `python -m compileall -q apps/web_portal apps/notify_cronjob_service
  functions/line_webhook_handler shared_lib/shared_module/portal_data tools
  tests/portal_data`：passed。
- 重建 `shared_lib-0.0.1.tar.gz`，複製到 Web Portal、LINE webhook、notify cron
  三個本機 deployment unit，並以 `--no-cache-dir --no-deps
  --no-build-isolation --force-reinstall` 安裝本機 artifact：passed，未下載依賴。
- 離線 preflight：`legacy_unfrozen` passed；shared source fingerprint：
  `bd3d932b5c5dc55695d73a203ffe9efbe24405fffd356993bcf7fc53a33a2298`。
- controller 以 implementation commit 與上述 fingerprint 驗證目前
  legacy-unfrozen → legacy-unfrozen：`status=valid`、`step_count=0`。
- `git diff --check` 與 staged diff check：passed。

## Black／isort 本機限制

- bundled Windows Python 下，Black 24.4.2 的多檔／連續 CLI 在 TASK-076 與
  TASK-077 皆曾持續高 CPU 停滯。本輪再以單檔
  `python -m black --check --workers 1 apps/web_portal/app.py` 重現，30 秒
  timeout，不能宣稱該 CLI check passed。
- timeout 已終止程序；後續 `Get-Process python` 未發現殘留 process。
- 依 repository 的 `make format` 順序，先對受影響檔案執行 isort，再用相同
  Black 24.4.2 的 `format_file_in_place` API 完成格式化。最後以
  `format_file_contents` API 對 15 個採 Black 風格的受影響檔案做純內容比對，
  全部 unchanged。
- notify app、LINE 固定訊息模板及三個既有非 Black baseline tests 只保留必要
  行為／fixture diff，避免無關整檔重排。hosted Python 3.10 Black CLI 與 final
  gate 尚待 Work 建立 ready PR 後補證，未將本機 hang 記為 passed。

## 未驗證與限制

- 未執行 hosted Python 3.10 CI、Docker／Cloud Build、部署、production metadata
  或 revision inspection。
- 未連線任何 production 或 local PostgreSQL，未讀取真實 env／Secret，未修改
  IAM、Scheduler、traffic 或正式 flags，也未發送 LINE／Discord 通知。
- repository freeze 是 sequential rollout 的安全邊界，不是 atomic cross-service
  update，也不授權 TASK-078 feature-off deployment 或 TASK-079 activation。
- 因本 task 修改 classifier 本身，這個 PR 的保守分類可能仍跑 full hosted suite；
  contract test 證明後續只有已列 rollout freeze boundary 的變更不會無故選取 DB
  matrix。

## Work 驗收重點

- 查驗 freeze guard 順序與零副作用 mock assertions，尤其 webhook 固定 reply 與
  Portal auth／CSRF 先於 freeze。
- 查驗 controller canonical forward／rollback order、mixed-unfrozen fail-closed、
  stale commit／fingerprint rejection 與 output redaction。
- 在 hosted Python 3.10 執行唯一 ready PR 的 change-aware final gate，補上本機
  Black CLI 無法提供的證據。

## Work changes_requested 修正

- Work 發現 `shared_lib/shared_module/portal_data/runtime.py` 原先僅選取
  `deployment_tools`，會漏跑三個直接 consumer suites。已於
  `9d46aa3357734e2c5853a613ccfd860d5a16cb8e` 將該單檔精準分類為
  `deployment_tools`、`web_portal`、`line_webhook` 與 `notify_cron`；仍不選取
  `portal_data`，避免本任務範圍無關的 PostgreSQL matrix。
- `tools/phase_c_rollout_preflight.py` 與
  `tools/phase_c_transition_controller.py` 等既有 deployment boundary 仍只選取
  `deployment_tools`。新的 classifier regression tests 覆蓋兩種向量。
- 已執行：
  `python -m unittest tools.tests.test_ci_change_classifier
  tools.tests.test_deploy_phase_c_runtime
  tools.tests.test_deploy_phase_c_transition_controller -v`，33 passed；另以 CLI
  helper 輸出確認 runtime 為四個 scope、controller/preflight 僅為
  `deployment_tools`。`compileall`、Black 24.4.2 formatter API 內容比對與
  `git diff --check` 均通過。
