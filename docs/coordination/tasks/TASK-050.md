# TASK-050：以實際 legacy schema 進行離線 migration rehearsal

## 目標

將 TASK-048 的本機 PostgreSQL rehearsal 從最小 `members`／`games` fixture 升級為已由
TASK-049 唯讀盤點確認的 production-compatible legacy fixture，並離線驗證 Person／Event
expand schema 能與 `bigint` legacy IDs、RLS enabled tables、LINE identity 狀態及
append-only attendance history 安全共存。

這是 migration readiness task，不是 production migration task。

## 已確認背景

- TASK-049 去識別化逐欄 catalog evidence 已保存於
  `docs/operations/data/TASK-049-SUPABASE-CATALOG-SANITIZED.md`，Codex 應以該文件而非
  對話或 production 連線作為 fixture fidelity 的輸入。
- Supabase production 使用 PostgreSQL 15.1，`ntubtob` 有 10 張 legacy tables，所有 table
  啟用 RLS，沒有 `ntubtob.alembic_version`。
- `members.id`、`games.id`、`line_users.id`、`game_attendance_replies.id` 是 `bigint`
  identity；TASK-048 local fixture 和部分 adapter 仍以 `integer` 表示 Member/Game ID。
- Production 有 197 Members、65 LINE users、128 Games、1,648 attendance rows。
- Attendance history 有 1,495 個 game/member current-state groups；153 transitions 中 144
  是狀態變更、9 是連續相同回覆。沒有 orphan、exact duplicate、timestamp tie、identity
  change 或 Member/LINE mismatch。
- `games.cancellation_time` 有資料，但 `cancellations` table 為空。

## 工作範圍

### 1. Exact local legacy fixture

修改 local-only fixture，使其建立下列 `ntubtob` tables 的 production-compatible 結構：

- `attendance_reply_types`
- `ballparks`
- `cancellations`
- `discord_webhooks`
- `game_attendance_replies`
- `games`
- `line_groups`
- `line_notify_tokens`
- `line_users`
- `members`

要求：

- 依 TASK-049 catalog evidence 使用 `bigint` identity、已確認欄位、nullable、defaults、
  FK 與 RLS enabled flags；不複製任何 production row value。
- fixture data 只能為明顯虛構內容，至少覆蓋：linked LINE user、pending candidate、ignored
  identity、正常／已取消 game、真正回覆變更、連續同回覆與空 `cancellations` table。
- fixture setup 必須 idempotent，僅接受既有 local database gate 的 URL。

### 2. Migration／model fidelity

- 將 `LegacyMemberRecord`、`LegacyGameRecord` 及 activity-to-game relation 校正為 `bigint`
  相容型別。
- 不重寫已合併的 `0002_portal_data_foundation` revision。若 local rehearsal 需要演進，新增
  一個描述性 Alembic revision，讓 `0001` → `0002` → 新 revision 的 chain 可重現。
- 保持 production rollback 原則：未來出問題回退 application，不 destructive downgrade
  production expand schema。

### 3. Deterministic attendance projection rehearsal

新增只供 local rehearsal 使用的 domain/helper 或 test fixture，將 legacy history 投影為
每個 `(game_id, member_id)` 一筆 current state：

- 明確採 `updated_at DESC, id DESC` 決定最新 row。
- 不修改、刪除或加 unique constraint 到 legacy attendance table。
- 顯示／測試 projection counts，不輸出真實或類 production identity values。
- 驗證連續同回覆不影響最終 current state，真正變更以最後版本為準。

### 4. Offline verification

新增或調整離線測試，至少驗證：

- exact fixture 的主要 columns、`bigint` IDs、FK、RLS enabled flags 與空 cancellations。
- Alembic 從 exact fixture stamp `0001` 到 head 可升級；降至 `0001`、重建 fixture、再升級
  仍可重現。
- Person/member backfill 仍 idempotent，fake seed 仍只使用假資料。
- attendance projection 的 state-change、same-reply、tie-breaker case。
- 既有 portal-data PostgreSQL contract suite 持續通過。

## 非目標

- 不連線、查詢、stamp、DDL、backfill 或寫入 Supabase production。
- 不讀取 `envs/**/.env.yaml`、connection string、token 或 Secret。
- 不將 local fixture 內任何假資料上傳或帶入服務 request path。
- 不把 legacy game attendance 實際回填至新 Event tables。
- 不決定 ignored LINE user 要映射為 `blocked` 或 `disabled`；只在 fake fixture 表示 legacy
  `ignored`，正式映射保留給 Owner 核准的 backfill task。
- 不為 RLS enabled／zero policy 的 production runtime 行為下結論，也不新增 production RLS
  policy。
- 不修改 Web Portal、LINE webhook、Scheduler、Cloud Run、Cloud Build、Secret、IAM 或部署設定。
- 不 push、建立 PR、merge 或部署。

## 設計決策

- Legacy attendance 是 append-only history；新 current-state projection 是衍生讀模型，兩者
  不互相取代。
- `updated_at DESC, id DESC` 是 deterministic tie-breaker；不依賴 PostgreSQL 未排序 row order。
- 所有 DDL 僅針對 local Docker PostgreSQL 與其明確的 `ntubtob_portal_local` database。
- 本機 RLS flags 旨在重現 production metadata，不構成 production policy 或 access decision。

## 驗收條件

1. local-only database gate 仍拒絕 remote／Supabase URL。
2. `tools.setup_portal_data_legacy` 在乾淨 local DB 建立完整 fake legacy fixture，重跑不失敗。
3. `alembic stamp 0001_legacy_baseline`、`alembic upgrade head`、`alembic current` 完整通過。
4. downgrade/rebuild/upgrade rehearsal 通過；只允許移除 task-owned local DB objects。
5. fake seed 與 member backfill idempotent。
6. deterministic attendance projection 測試通過，涵蓋 state change、same reply 與同 timestamp
   的 ID tie-breaker。
7. `tests/portal_data` PostgreSQL suite、affected compile/import checks 與 `git diff --check` 通過。
8. Codex report 清楚說明本次未連線 production、未執行 production migration、未處理 Secret。

## 必要驗證命令

```powershell
docker compose -f docker-compose.portal-data.yml config
docker compose -f docker-compose.portal-data.yml up -d portal-postgres
$env:PORTAL_DATA_DATABASE_URL = "postgresql+psycopg2://portal_local:local-only-password@127.0.0.1:55432/ntubtob_portal_local"
py -3.10 -m tools.setup_portal_data_legacy
py -3.10 -m alembic stamp 0001_legacy_baseline
py -3.10 -m alembic upgrade head
py -3.10 -m unittest discover -s tests/portal_data -v
py -3.10 -m compileall -q shared_lib/shared_module tools migrations tests/portal_data
git diff --check
git status --short
```

若本機缺少 `py -3.10`，Codex 應如實記錄，仍可用可用 Python 執行並做 Python 3.10 grammar
compatibility check；不得因此修改 production runtime。

## 已知風險與待後續決策

- `ignored` legacy LINE user 的新 identity status（`blocked` 或 `disabled`）尚未由 Owner 決定。
- 新 tables 的 production RLS policy、database role、Supabase API exposure 與 migration
  baseline stamp 尚未設計或授權。
- 不可從 aggregate-only evidence 判斷 21-version attendance group 的業務原因；rehearsal 應
  驗證機制，不應查詢 production row values。
- 此任務不會證明 production lock time、PITR、backup 或 deployment compatibility。

## Base commit

`b5689ec`
