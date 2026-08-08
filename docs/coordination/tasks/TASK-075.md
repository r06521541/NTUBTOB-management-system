# TASK-075：建立 change-aware CI 與單一 final gate

## 任務目標

將目前所有 PR／main push 一律啟動 PostgreSQL 15／16 與全部服務測試的 workflow，改為可離線測試、
fail-conservative 的變更分類流程。一般純文件只走快速 gate；受影響程式執行對應 suite；database 與受控
artifact 變更仍執行 PostgreSQL 15／16 matrix。所有路徑最後匯入一個名稱穩定的 final gate，供未來 branch
protection 使用。

本任務同時承接 Owner 已審閱的協作規範文字；不得把這些既存文件變更拆成另一個 PR 或先觸發 CI。

## Base 與既存變更

- Base commit：`945375c82761efe9a19e5a477c53f7fd4d3c5c49`
- 修改前必須執行 `git status --short`。
- 下列既存未提交變更屬 Owner 已審閱的 Work policy changes，必須保留，不得覆寫、還原或宣稱為 Codex實作：
  - `AGENTS.md`
  - `docs/coordination/COLLABORATION.md`
  - `docs/coordination/DECISIONS.md`
  - `docs/coordination/HANDOFF.yaml`
  - `docs/coordination/PROJECT_STATE.md`
  - `docs/coordination/tasks/TASK-073.md`
  - `docs/operations/data/PORTAL_DATA_PHASE_C_PRODUCTION_READINESS.md`
- 本任務文件 `docs/coordination/tasks/TASK-075.md` 亦由 Work 建立。

## 已確認現況

- `.github/workflows/python-tests.yml` 對每個 `pull_request` 及每次 `main` push 都跑兩個完整 matrix jobs。
- 每個 job 都安裝全部依賴、啟動 PostgreSQL、驗證 Phase C artifacts，並執行 portal-data、Web Portal、
  game broadcast、notify cron、deployment wrapper、schedule function及LINE webhook suites。
- GitHub目前回報`main`沒有branch protection；本任務不得修改repository settings。
- PR CI與merge後main push會重複執行同一組昂貴tests。

## 設計要求

### 1. 可測試的變更分類器

- 建立Python 3.10相容、無第三方依賴的classifier helper及離線unit tests。
- 輸入為repository-relative changed paths；輸出至少包含：
  - `docs_only`
  - `portal_data`
  - `web_portal`
  - `game_broadcast`
  - `notify_cron`
  - `deployment_tools`
  - `update_schedule`
  - `line_webhook`
  - `full`
- 未知、無法解析、空白但非明確docs-only、workflow自身、dependency／shared interface等高影響變更必須
  fail conservative，不能錯誤分類為docs-only。
- `docs/operations/sql/**`、migration／model／portal-data verifier、database tests、`.gitattributes`及database
  workflow boundary不得分類為一般文件。
- `shared_lib`變更須依callers保守觸發所有直接受影響suite；無法安全細分時使用`full`。

### 2. Workflow行為

- 保留`pull_request`、`main` push及`workflow_dispatch`觸發；本任務不移除main safety net。
- 加入PR／branch scoped concurrency與`cancel-in-progress`，只取消同一ref的過時run。
- 使用官方actions並維持immutable SHA pinning；不得新增未審核第三方path-filter action。
- Workflow必須可靠取得PR base與head間、main push before與after間的changed paths；`workflow_dispatch`與
  無法可靠取得diff的情況走`full`。
- 一般純文件只執行快速gate，不啟動PostgreSQL container、不安裝完整application dependencies。
- Database範圍繼續以Python 3.10跑PostgreSQL 15.8／16.4 matrix、Black、Phase C artifact verifier及完整
  portal-data suite。
- 各服務只在相應scope或`full`時執行；避免為了單一服務重複啟動PostgreSQL matrix。
- 提供名稱穩定且永遠執行的final aggregate gate；任何required child job failure、cancel或分類失敗都使final
  gate失敗，合法skip不應誤判失敗。
- Dependency cache只能使用官方setup action支援、以lock／requirements內容為key的安全cache；若無法安全
  實作可留待後續，不得使用跨trust boundary的任意cache key。

### 3. PR與main證據

- 本任務先保留change-aware main push驗證；不得因`main`目前未受保護就移除安全網。
- 未來取消merge後昂貴重跑的前置條件是Owner另行批准並完成branch protection／禁止direct push；不在本任務範圍。
- 本次workflow本身變更必須走`full`，作為新分類與matrix的基準證據。

## 非目標與禁止事項

- 不修改production、Supabase、schema、migration SQL或checksum。
- 不部署、不操作Secret／IAM／Scheduler／Cloud Run／Cloud Functions，不發送通知。
- 不修改GitHub repository settings、branch protection、environment或credentials。
- 不新增大型CI framework，不重構application code。
- 不為既存policy文件另外commit／push／PR。

## 必要測試

- Classifier unit tests至少覆蓋：
  - 一般Markdown／coordination docs → docs-only。
  - `docs/operations/sql/**`與`.gitattributes` → portal-data／full，絕非docs-only。
  - 各app/function及其tests → 對應scope。
  - migrations、models、portal-data helpers/tests → PostgreSQL matrix。
  - shared library、requirements、workflow、未知路徑 → conservative full或明確的安全superset。
  - Windows separator、前置`./`、重複path、空輸入與惡意換行／GitHub output injection不得造成scope逃逸。
- Workflow YAML可由可用parser解析；若本機沒有parser，使用repository可用的安全替代並由hosted GitHub parser補證據。
- 執行所有classifier／workflow contract tests。
- 因workflow自身改變，本次final PR須成功執行PostgreSQL 15／16及所有既有服務suites一次。
- `git diff --check`與`git status --short`。

## 交付與驗收流程

1. Codex直接在目前工作樹建立task branch，保留上述既存policy changes。
2. Codex實作、執行本機測試、建立描述性commit並push；report需區分Work既存文件與TASK-075實作。
3. 預設不提前建立Draft PR；handoff設為`ready_for_review / work`。
4. Work驗收shared branch後，將review／handoff併入同一final branch，建立唯一一個ready PR。
5. 由於workflow自身改變，該PR必須取得一次完整hosted baseline；通過後依standing Git授權squash merge。
6. 不另開純closeout／run-ID／merge-metadata PR。

## 完成定義

- 純一般文件PR不會啟動PostgreSQL或完整application suites。
- Database與受控artifact變更仍跑雙PostgreSQL matrix。
- 各服務變更觸發正確suite，未知路徑fail conservative。
- Final aggregate gate不會因合法skip失敗，也不會掩蓋child failure／cancel。
- PR與main push行為有離線contract tests及一次hosted full baseline。
- 已審閱policy文件與TASK-075實作在同一個PR交付。
- 未執行任何production或GitHub settings變更。
