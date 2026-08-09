# TASK-075 Codex report

## 任務狀態

- 狀態：`ready_for_review`
- Branch：`codex/task-075-change-aware-ci`
- Base commit：`945375c82761efe9a19e5a477c53f7fd4d3c5c49`
- Implementation head：`cd76a94924f237d6eb464f4be4d58e5a51864b72`
- PR：依任務預設未建立；Work驗收shared branch後建立唯一ready PR

## Codex實作

- 新增Python 3.10／stdlib-only classifier，輸入repository-relative paths，輸出固定
  `docs_only`、七個suite scopes及`full`布林值。一般文件才是docs-only；database artifacts、workflow、
  dependencies、shared library、未知或畸形path均fail conservative。
- Git diff使用NUL分隔；PR使用base/head merge-base，main push使用before/after。無效SHA、zero SHA、
  missing object、diff錯誤、空diff或惡意newline均走full，且GitHub output只含固定key與布林值。
- Workflow保留pull request、main push及manual dispatch；manual dispatch與未知event走full。加入以workflow及
  PR number／ref為範圍的concurrency與`cancel-in-progress`。
- Docs-only只執行checkout、Python setup、changed-line check及20項classifier／workflow contracts，不啟動
  PostgreSQL、不pip install application dependencies。
- Portal-data保留PostgreSQL 15.8／16.4 matrix、Black、三個Phase C verifier及完整suite；七個非DB scopes
  只執行對應suite，避免重複啟動database matrix。
- 新增名稱固定的`CI final gate`。它永遠評估全部child results，接受未選job的合法skip；classification、quick
  或任何已選job failure／cancel／skip均非success。Aggregate不checkout或下載action，避免`always()`在取消
  流程中執行可能阻塞的網路步驟。
- setup-python pip cache只用於portal-data job，key由`requirements-migrations.txt`內容產生；未加入第三方
  path-filter action，所有official actions維持immutable SHA pin。

## Owner-reviewed既存文件（非Codex實作）

下列變更在Codex接手前已存在，屬Owner審閱的Work policy bundle；Codex完整保留並與TASK-075實作放在同一
implementation commit，未拆成另一個commit／push／PR：

- `AGENTS.md`
- `docs/coordination/COLLABORATION.md`
- `docs/coordination/DECISIONS.md`
- `docs/coordination/PROJECT_STATE.md`
- `docs/coordination/tasks/TASK-073.md`
- `docs/operations/data/PORTAL_DATA_PHASE_C_PRODUCTION_READINESS.md`
- `docs/coordination/tasks/TASK-075.md`
- `docs/coordination/HANDOFF.yaml`的接手前狀態；Codex只在完成時更新交棒欄位與note

## Codex新增／修改檔案

- `.github/workflows/python-tests.yml`
- `tools/ci_change_classifier.py`
- `tools/tests/test_ci_change_classifier.py`
- `tools/tests/test_ci_workflow_contract.py`
- `docs/coordination/reports/TASK-075-CODEX.md`
- `docs/coordination/HANDOFF.yaml`（僅completion handoff）

## 驗證結果

- `python -m unittest discover -s tools/tests -p "test_ci_*.py" -v`：20/20 passed；包含docs-only、所有
  scopes、database boundaries、Windows separator、`./`、duplicates、empty／unknown／newline paths、
  fixed outputs、PR merge-base、diff failure、final success／failure／cancel／skip及實際Bash aggregate。
- `python -m unittest discover -s tools/tests -v`：61/61 passed。
- Web Portal：120 tests，共118 passed、2個Windows platform skips。
- Game broadcast：28/28 passed。
- Notify cron：9/9 passed。
- Update schedule：5/5 passed。
- LINE webhook：19/19 passed；預期500測試有Flask error log但assertion通過。
- Local `postgres:15.8-alpine`（實際15.8）：完整portal-data 157/157 passed。
- Local `postgres:16.4-alpine`（實際16.4）：完整portal-data 157/157 passed。
- `python -m compileall -q tools/ci_change_classifier.py tools/tests/test_ci_change_classifier.py
  tools/tests/test_ci_workflow_contract.py`：passed。
- Black 24.4.2（3個新增Python files）：passed。
- `git diff --check`及staged diff check：passed。
- 對base至implementation head執行classifier：只有`full=true`，符合workflow自身變更必跑full baseline。
- 兩個task-owned localhost containers、networks及fake-data volumes均已移除。

## 未執行與剩餘風險

- 本機沒有可用的YAML parser／actionlint；以stdlib workflow structural contracts、實際Bash aggregate及GitHub
  官方context規格作安全替代。依TASK-075流程，Work驗收後建立的唯一ready PR仍須由GitHub hosted parser接受，
  並成功執行一次full baseline與穩定`CI final gate`。
- 尚未以實際hosted docs-only PR觀察PostgreSQL及application jobs為`skipped`；這是final PR成功後下一個真實
  docs-only變更才能證明的營運證據，本次離線tests已覆蓋分類與aggregate語意。
- 未新增change detection以取消main safety net；main push仍保留。未修改branch protection或任何GitHub settings。
- 未修改database schema、migration SQL、checksum、application code或production runtime設定。
- 無production／Supabase連線、migration、deployment、Secret／IAM／Scheduler／Cloud資源或真實通知操作。
- Completion commit前只剩本report及HANDOFF；commit後預期工作樹乾淨。

## Owner決策

目前不需要新產品或production決策。Work須先驗收shared branch，再依既有授權建立唯一ready PR並確認完整hosted
baseline；本任務不授權production或repository settings變更。
