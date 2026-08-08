# TASK-076：Phase C 跨服務啟用準備與本機整合演練

## 任務目標

在 production database 已完成 `0004_phase_c_identity_lifecycle` expand-only migration、所有 runtime flags 仍關閉的前提下，完成 Phase C application rollout 的 repository-only 安全準備。建立 Web Portal、LINE webhook、notify cron 與 shared library 之間可重現的跨服務資料契約、旗標狀態機、本機 PostgreSQL 整合測試、部署前檢查及分階段啟用／回復 runbook。

本任務不部署、不操作 production，也不開啟任何正式環境旗標。交付目標是讓後續 TASK-077 能以精確版本、服務順序、觀察條件與 rollback boundary 另行取得 Owner 部署批准。

## Owner 已批准範圍

- Owner 已於 2026-08-08 批准 TASK-076 repository-only 實作與既有一般 Git／GitHub 工作包。
- Codex 可在 task branch 內實作、測試、建立描述性 commit、push 並交回 Work 驗收。
- Work 驗收通過後可建立唯一一個 ready PR，執行一次必要的 final hosted CI，成功後依 standing authorization squash merge。
- 不為 task／handoff／report／review 等純流程文件另外建立 PR 或觸發昂貴 CI。
- Production deployment、runtime flag 修改、production DB 操作、Secret／IAM／Scheduler／cloud resource 修改及真實通知不在本批准內。

## Base 與工作樹

- Base commit：`893e365`
- 目前 task branch：`codex/phase-c-rollout-planning`
- 修改前執行 `git status --short`；保留並區分所有既存變更。
- `893e365` 是 TASK-073 production migration closeout 的純文件 commit，尚未 push；TASK-076 應承接此 commit，不得重寫或遺失。

## 已確認事實

- Production schema 已由 Owner 執行並驗證為 `0004_phase_c_identity_lifecycle`；post-check 與 inventory comparison 均為 `pass`。
- `PORTAL_DATA_PHASE_C_ENABLED` 在 Web Portal、LINE webhook 與 notify cron 的 example env 中預設為 `"false"`，只有精確字串 `true` 才可啟用。
- Web Portal 另有 `WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED`，預設為 `"false"`。
- Phase C application bridge、Person identity lifecycle、Person-based attendance 及相關 local-only 行為已在 TASK-070 建立。
- 正式 runtime flags 仍關閉；TASK-073 未部署 application，也未開啟 identity maintenance。
- Repository 已有 change-aware CI 與穩定的 `CI final gate`；shared library、database contract 或高影響變更會保守執行必要 suites。

## 工作範圍

### 1. 跨服務 caller 與資料流盤點

- 搜尋並確認 `PORTAL_DATA_PHASE_C_ENABLED`、identity maintenance、portal-data repository、attendance analyzer 及 Phase C models 的所有 callers。
- 建立可驗證矩陣，至少涵蓋：
  - Web Portal：LINE principal/session、Member 配對、Person／qualification 管理、出席讀寫與管理頁。
  - LINE webhook：出席回覆與 Person／Member projection。
  - notify-cronjob-service：出席統計、提醒資料來源與顯示名稱。
  - shared library：共同 repository、models、runtime helper、attendance analyzer 及部署 artifact。
- 查證 `game_broadcast_service` 是否為直接 caller；若不是，明確排除，不因保守猜測擴張程式修改。
- 記錄各部署單元是否必須重建／複製 `shared_lib-0.0.1.tar.gz`。

### 2. 功能旗標狀態機與 fail-closed 契約

定義並以自動化測試驗證：

| Phase C | Identity maintenance | 預期行為 |
| --- | --- | --- |
| off | off | 完整維持 legacy 行為 |
| on | off | 可使用 Phase C runtime，但禁止管理者身分異動 |
| on | on | 可使用完整 Phase C 與身分管理功能 |
| off | on | 不合法；必須 fail closed，不能開放管理功能 |

- 缺少、空白、大小寫不同或非精確 `true` 均視為 off。
- 不合法組合不得默默形成部分 auth bypass；採最小且可測試的拒絕、停用或安全啟動檢查。
- Demo mode 不得連 production DB，也不得因 Phase C／maintenance flag 形成正式身分繞過。
- 不把機密值寫入 log、錯誤訊息或測試輸出。

### 3. PostgreSQL 0004 跨服務整合測試

使用本機 PostgreSQL、repository migration 與明顯虛構資料建立可離線重跑的 integration fixture。至少驗證：

- schema 0004 搭配所有 flags off 時，legacy 路徑仍可運作。
- 新版程式在 flags off 時不會意外建立或修改 Phase C identity data。
- LINE Member 配對建立／連結正確 Person，並依已批准規則授予 active `team_player`。
- Web Portal 與 LINE webhook 對同一人的出席讀寫結果一致。
- notify cron 讀到與 Portal／Webhook 相容的 attendance projection。
- active bounded `guest_player` 可回覆既有比賽出席；過期、revoked 或無資格者不得取得該能力。
- blocked Person、暫停參與 Person 與 revoked qualification 不會因登入、重配或一般 attendance request 自動恢復。
- 重複請求、雙擊或重試不產生重複 identity、qualification、attendance 或 audit side effect。
- display name／formal name 的既定可見性契約不因服務不同而漂移。
- 所有 LINE、Discord、crawler、weather、GCP 與 production database 呼叫均 mock／stub；測試不得需要真實 secret。

若現有測試架構不適合一次啟動三個 Flask／Functions entry points，可在同一 PostgreSQL fixture 下以 service-level integration tests 驗證共同 repository contract；不得為追求形式而全面重寫服務。

### 4. 混合版本與 rollout 過渡狀態

以自動化測試或具體 contract tests 驗證並分類下列狀態：

- schema 0004 + 目前 production application + flags off。
- schema 0004 + 新 application artifacts + flags off。
- Web Portal Phase C on、Webhook／notify off。
- Webhook Phase C on、Portal／notify off。
- notify Phase C on、Portal／Webhook off。
- 三個服務 Phase C on、identity maintenance off。
- 三個服務 Phase C on、identity maintenance on。
- 任一階段將 flags 關閉或流量切回前一 revision。

若某個混合狀態無法安全支援，必須在 runbook 列為禁止狀態並用精確部署／啟用順序避免；不得用未驗證假設宣稱相容。

### 5. 部署 artifact 與 preflight

- 檢查 Web Portal、LINE webhook、notify cron 的 deployment wrapper／Make target 與 env example contract。
- 建立或補強可離線執行的 preflight，至少檢查：
  - 所需旗標存在時的精確值與缺省 fail-closed 行為。
  - maintenance 不可在 Phase C off 時有效。
  - shared library artifact 與 source／預期版本一致，且三個部署單元取得正確 artifact。
  - build context 不包含 `.env.yaml`、credentials、private backup、local database artifact 或無關 dist 內容。
  - preflight 不輸出 secret 值。
- 不得執行 `gcloud` mutation、Cloud Build、Cloud Run／Functions deploy 或 production smoke request。

### 6. 分階段 rollout／rollback runbook

建立精確而可執行的後續操作文件，至少包含：

1. 部署三個服務的新 artifacts，但 flags 保持 off。
2. 以無副作用 health checks 與既有行為 smoke checks 驗證 feature-off deployment。
3. 依本任務證據列出 Phase C 各服務的安全開啟順序、每階段觀察時間與停止條件。
4. 三個服務 Phase C 一致後，才允許最後開啟 identity maintenance。
5. 每階段的唯讀驗證、log 指標、允許／禁止的人工操作。
6. 第一層 rollback 為 flags off；第二層為 100% traffic 回前一個已知良好 revision。
7. Schema 保留 0004；緊急 rollback 不執行 destructive downgrade、DROP 或 production data cleanup。

Runbook 必須把仍需 Owner 明確批准的 production deployment、flag mutation 與 rollback traffic mutation 標示清楚。

## 非目標與禁止事項

- 不部署、不執行 Cloud Build、不修改 production runtime flags。
- 不連線或寫入 production Supabase，不執行 DDL／DML／migration／backfill／cleanup。
- 不修改 Secret、IAM、Scheduler、Cloud Run、Cloud Functions、GitHub repository settings 或 branch protection。
- 不發送真實 LINE／Discord 通知，不人工 invoke production endpoint。
- 不新增 schema 0005，不修改正式 schema，不重新設計 Phase C core model。
- 不實作 Google／Apple OAuth、新活動類型、旅遊群組、event eligibility 或大型 UI 改版。
- 不全面重寫 Flask apps、shared library 或 deployment tooling。

## 必要驗證

Codex 應依實際 diff 執行最小充分但完整的本機驗證，至少包括：

- 新增的 flag state machine／preflight unit tests。
- PostgreSQL 15 或 repository 可用的受控本機 PostgreSQL 0004 integration tests。
- Web Portal 受影響 tests。
- LINE webhook 受影響 tests。
- notify cron 受影響 tests。
- shared library 直接受影響 tests，並重建／安裝 shared library artifact。
- deployment tooling contract／dry-run tests（若有修改）。
- Python 3.10 compile／import check。
- 外部請求與 production DB zero-call assertions 或等價 mock 證據。
- `git diff --check`。
- `git status --short`，並區分既存 TASK-073 closeout commit 與本次變更。

本機環境若缺少全域 `python`、Unix `make/sh` 或 PostgreSQL，不得修改產品程式規避；應優先使用 repository 已配置的 Python runtime、Windows 等價命令或既有 container／test harness。仍無法執行的部分必須精確回報，交由 final hosted CI 補證據。

## 交付與協作流程

1. Work 建立本 task 與 `ready_for_codex / codex` handoff，並以跨 session 訊息交給固定的「Codex－實作」task。
2. Codex 開始前閱讀 `AGENTS.md`、`COLLABORATION.md`、`HANDOFF.yaml`、本 task、TASK-070／071／073 相關 report／review及相鄰程式碼。
3. Codex 在目前 task branch 實作、測試、建立描述性 commit並push；不得先建立 Draft PR。
4. Codex 在完成、中斷、遇到範圍疑義、發現 blocking finding 或需要 Work 驗收時，必須以跨 session 訊息主動通知 Work；不得只留在自己的對話等待 Owner 轉述。
5. Work 收到通知後查驗實際 branch、commit、diff 與測試。若需修正，更新 `changes_requested / codex` 並以跨 session 訊息退回；雙方持續往返，直到 Work accept 或需要 Owner 決策。
6. Work accept 後加入單一驗收 commit，建立唯一 ready PR，查驗 change-aware final hosted CI；成功後依 standing authorization squash merge。
7. 不為跨 session 通知、狀態時間戳、CI run ID 或 merge metadata建立獨立 commit／PR。

## 完成定義

- 三個 runtime services 與 shared library 的 callers、artifact 與資料流已由程式碼證據確認。
- 合法／不合法旗標組合均有 fail-closed automated tests。
- PostgreSQL 0004 的 Portal／Webhook／notify attendance 與 identity lifecycle 契約可離線重跑。
- 所有可安全支援及禁止的 mixed-mode 狀態已明確列出並有測試或證據。
- Feature-off deployment、分階段 activation、觀察、停止與 rollback 流程可直接轉成 TASK-077 exact production work package。
- 未接觸 production、未洩漏 secret、未產生真實通知或其他外部副作用。
- Work 實際驗收完成，唯一 final PR 的必要 CI 成功，並以 squash merge 進入 default branch。
