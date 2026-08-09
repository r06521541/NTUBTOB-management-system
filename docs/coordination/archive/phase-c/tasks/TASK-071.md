# TASK-071：Phase C production migration readiness 與精確執行包

## 任務目標

在不連線、不修改 production Supabase 的前提下，將已合併的 Phase C `0003 -> 0004` migration 整理成可稽核、
可重現、fail-closed 的 production readiness package。交付內容必須讓 Work 能先用去識別化的唯讀 production
inventory 判斷是否具備執行資格，並讓後續獨立任務在 Owner 明確批准 exact commit、SQL checksums、時間窗與
stop/recovery boundary 後，才可能執行 migration。

本任務只準備工具、SQL artifacts、validator、runbook 與本機 PostgreSQL 16 證據；不得執行 production migration、
不得部署、不得啟用 `PORTAL_DATA_PHASE_C_ENABLED` 或 identity maintenance。

## 已確認基線

- Base commit：`6c4be4963fc2febe9032cc8fb48fc3f167064b3e`。
- TASK-070 已由 PR #68 squash merge；Phase C application 與 Alembic revision
  `0004_phase_c_identity_lifecycle` 已在 repository，但尚未授權 production migration、runtime rollout 或 feature enablement。
- 已知 production migration revision 為 `0003_legacy_bigint_activity_game`；Phase B 已完成 197 個 Member/Person link、
  56 個 linked LINE identities、56 個 active `team_player` 與 309 個 append-only audits。這些是歷史確認值，
  不得視為執行當下的新鮮證據。
- Production runtime 目前仍走 legacy path；`PORTAL_DATA_PHASE_C_ENABLED` 與 identity maintenance 均未獲准啟用。
- Web Portal admin authority 仍是 `WEB_PORTAL_ADMIN_MEMBER_IDS`；本任務不做 People-role cutover。
- Owner 先前接受 migration window 的 transaction-local timeout 基準：`lock_timeout = 5s`、
  `statement_timeout = 60s`。若實際 SQL 無法在此界線內完成，只能停止並回報，不得自行放寬。

## 交付範圍

### 1. 唯讀 production inventory artifact

建立固定、checksummed、單一 transaction 的 read-only SQL，至少輸出：

- connection/session：server major、current revision、transaction read-only、schema ownership relation、session privilege risk；
- Phase A/B contract：legacy 10 tables、portal tables、columns、PK/FK/check constraints、indexes、RLS/forced-RLS/policies、
  append-only audit triggers與 grants 的 aggregate/fingerprint；
- exact Phase B invariants：Member/Person links、LINE identity projection、team_player、audit relationships及 cross-model drift；
- Phase C collision gates：`0004` 新增的 columns/tables/constraints/indexes 不得預先存在，且 Alembic 必須只有 0003；
- attendance readiness：所有既有 `game_attendance_replies.member_id` 都能解析到唯一 `members.person_id`，
  unresolved、orphan、duplicate/collision counts 必須為零；legacy row counts與最新回覆投影只輸出 aggregate；
- runtime/maintenance flags不是資料庫 evidence，不可由 SQL 假裝驗證，須明列為部署前獨立檢查。

輸出必須使用固定六欄 sanitized CSV contract：

```text
section,metric,status,boolean_value,integer_value,text_value
```

不得輸出 Member ID、Person ID、LINE subject、nickname、姓名、訊息內容、note、provider subject、URL、credential、
完整 connection string 或任何 application row value。

SQL 必須明確使用 `BEGIN TRANSACTION READ ONLY`、transaction-local timeout 與最終 `ROLLBACK`；未知或遠端 URL
不得進入 repository 測試工具。不要將 Supabase credential 寫入 command、log、fixture 或文件。

### 2. Exact migration artifact

- 從 Alembic revision 0003 精確 render 0004，產生 repository-owned SQL 與 SHA-256 sidecar。
- verifier 必須比對 Alembic source、revision graph、byte-for-byte內容與 checksum；任何手改、額外 head、placeholder、
  encoding/line-ending drift、缺少 transaction boundary 或未預期 DDL/DML 均 fail closed。
- migration artifact 只能包含 0004 已review的 expand/backfill：Person profile fields、review thread/message schema、
  audit actions、guest bound、attendance `person_id` bridge/FK/index與 deterministic compatibility backfill。
- 不新增 RLS policies/grants/roles，不修改 Secret/IAM/Scheduler，不引入其他 schema 或 ad-hoc cleanup。

### 3. Read-only post-check artifact

建立固定、checksummed post-check SQL與 strict validator，至少驗證：

- revision 精確為 0004 且 Alembic single head；
- 新 columns/tables/PK/FK/check/indexes 與 RLS zero-policy boundary 完全符合 repository contract；
- legacy row counts與既有 Phase B relationships未減少或漂移；
- 所有 attendance rows 的 `person_id` 已解析且與 `member_id -> members.person_id` 一致；
- migration compatibility backfill audit只允許 deterministic、可解釋的數量與關係；若 fresh inventory已是完整 Phase B，
  預期 `member_backfilled` delta為零；
- 沒有 unexpected audit action、orphan identity、duplicate provider subject、extra team_player或其他 cross-model drift。

提供 inventory/post-check compare，明確區分：pass、safe retry after confirmed rollback、ambiguous commit、semantic drift。

### 4. Execution-package runbook（不執行）

文件必須定義後續獨立 execution task 的唯一允許順序：

1. 確認 exact merged commit、三份 SQL checksums與 backup verification仍有效；
2. 宣告 30 分鐘 freshness window，短暫停止管理者執行 identity/member matching/remap/unlink與相關人工 SQL；
3. Owner 在 Supabase SQL Editor執行 exact read-only inventory並交回完整 sanitized CSV；
4. Work strict validate；任一 gate不符即停止；
5. 僅在新的 Owner exact approval 下執行一次 migration artifact；
6. 立即執行 exact read-only post-check並由 Work compare；
7. 結果明確成功後才可規劃 application deployment，runtime flags仍保持關閉。

Recovery boundary：

- migration error/timeout且transaction確認 rollback：修正原因前不得重跑；不得逐句補跑。
- connection loss或結果不明：先以 read-only revision/post-check判定，禁止直接重跑。
- transaction已commit但post-check語意失敗：保留 expand schema，停止 rollout，建立 forward-recovery task；
  不執行 production downgrade、DELETE/TRUNCATE、audit刪除、trigger停用或restore。
- application rollback與schema rollback分離；0004為expand migration，舊版 application與feature-off路徑必須可繼續運作。

### 5. Local PostgreSQL 16 rehearsal與測試

在 repository定義的 localhost-only PostgreSQL fixture驗證：

- clean 0003 -> 0004、fresh install、downgrade/upgrade rehearsal；
- attendance完整 backfill與 unresolved row atomic rollback；
- lock timeout、retry after confirmed rollback、mid-migration failure injection；
- inventory/post-check正常與每一項重要drift mutation的fail-closed測試；
- checksum、revision graph、line ending、encoding、placeholder、unexpected SQL mutation negative tests；
- fixture只使用明顯虛構資料，不讀取 `envs/**/.env.yaml` 或任何 Secret。

## 非目標與禁止事項

- 不連production DB，不執行Supabase SQL，不收集本任務以外的production evidence。
- 不執行 migration、DDL、DML、backfill、cleanup、downgrade、restore或production data修正。
- 不部署 Web Portal、LINE webhook、notify cron或其他服務。
- 不啟用 `PORTAL_DATA_PHASE_C_ENABLED`、`WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED` 或其他production flag。
- 不修改 Secret、Secret Manager、IAM、Scheduler、Cloud Run、Cloud Functions、Cloud Build或LINE/Discord設定。
- 不發送真實LINE/Discord通知，不人工invoke webhook、scheduler、cron或production endpoint。
- 不做People-role cutover、Person merge、Event eligibility、Event production persistence或Google/Apple OAuth。
- 不順手修remap UI非阻塞觀察或其他無關程式碼。

## 驗收條件

- inventory、migration、post-check均為deterministic repository artifacts並附SHA-256 sidecar。
- 三者各有strict verifier；mutation、checksum、revision、format與unsafe SQL negative tests完整。
- inventory與post-check僅輸出固定六欄sanitized aggregates，無識別資料或secret。
- 0003 -> 0004在local PostgreSQL 16可重現，failure/timeout/ambiguous recovery界線有測試與runbook。
- execution package清楚標出Owner下一次需要批准的exact commit、checksums、30分鐘window與stop/recovery boundary。
- 現有Phase C application、legacy fallback與其他服務行為不被修改。
- Codex report列出實際commands、結果、runtime版本、platform skips、未執行production事項及所有變更檔案。

## 最低驗證命令

Codex應依實際新增tool名稱補齊精確命令，至少執行：

```powershell
python -m unittest discover -s tests/portal_data -v
python -m tools.portal_data_phase_c_migration verify
python -m tools.portal_data_phase_c_evidence verify
python -m compileall -q migrations tools tests/portal_data
git diff --check
git status --short
```

PostgreSQL測試必須使用 `PORTAL_DATA_TEST_DATABASE_URL` 指向repository定義的localhost-only
`ntubtob_portal_local`；不得接受remote或Supabase URL。

## Codex交付文件

- production inventory SQL、migration SQL、post-check SQL與各自checksum sidecar；
- render/verify/strict validate/compare工具與離線測試；
- Phase C migration readiness/execution runbook；
- `docs/coordination/reports/TASK-071-CODEX.md`；
- 更新 `docs/coordination/HANDOFF.yaml` 為 `ready_for_review / work`。

## 交棒與授權邊界

Owner已批准本任務的repository-only實作、測試、描述性commit、push、PR與CI工作包；Work可在無blocking finding且
required CI通過後依既有Git授權squash merge。本授權不包含任何production database連線或操作、migration execution、
deployment、runtime flag enablement、Secret/IAM/Scheduler/Cloud resource變更或真實通知。

## Base commit

`6c4be4963fc2febe9032cc8fb48fc3f167064b3e`
