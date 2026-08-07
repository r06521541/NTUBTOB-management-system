# TASK-052：準備 Supabase Migration Access Boundary 唯讀盤點

## 目標

為 TASK-051 尚未解除的 production migration blockers 準備一份可由 Owner 在 Supabase SQL
Editor 手動執行的 read-only inventory，以及不含敏感資訊的結果模板與 Dashboard 查驗清單。
本任務只準備查詢、解析與文件，不連 Supabase、不執行 SQL、不修改 schema、role、grant、RLS、
backup 或任何雲端設定。

## 已確認背景

- TASK-051 已由 PR #55 squash merge 為 `705983b281e60d9f586552e46aab3dd894db5fd2`。
- Production migration 前仍未知：runtime DB role/table owner 關係、grants、RLS policies／bypass、
  Supabase API exposure、backup/PITR 與 catalog freshness。
- TASK-049 已保存去識別化 legacy catalog；不得重複匯出 application row values 或實際 role 名稱。
- Owner 選擇 SQL Editor 路線：Codex 準備查詢，Owner 之後另行決定是否親自執行並回傳結果。

## 工作範圍

### 1. Read-only SQL

新增一份單一 transaction SQL，必須：

- 以 `BEGIN READ ONLY` 或等價方式 fail closed，結束時 `ROLLBACK`。
- 只查 PostgreSQL catalogs／information_schema 與 session metadata，不查 application rows。
- 確認 PostgreSQL version、schema existence、10 張 legacy tables、`alembic_version` 是否存在、
  columns／constraints／RLS flags 的去識別 fingerprint 是否仍符合 TASK-049。
- 查出 table owner relationship、current session 的 generic capability flags、role attributes、grants、
  RLS policies 與 policy command／roles；輸出必須在 SQL 內轉成 generic labels、boolean、counts 或
  stable hashes，不得輸出 actual role／user／owner names、policy expressions、host、database name、
  DSN、Secret、row values 或精確 storage size。
- 標示新 portal-data tables 是否已意外存在，但不得讀取其 rows。
- 每個 result section 有固定名稱、欄位與 interpretation，方便 Work 驗證 CSV。
- 不使用 dynamic SQL、temporary function、DDL、DML、SET ROLE、SECURITY DEFINER、extension、
  network function 或 provider admin API。

### 2. Offline safety verifier

新增 Python 3.10-compatible static tests／verifier，至少拒絕：

- 非 read-only transaction、缺少 rollback；
- INSERT／UPDATE／DELETE／MERGE／COPY／TRUNCATE／DDL／GRANT／REVOKE／SET ROLE；
- application table row reads；
- current user、role name、owner name、policy expression、host／database／DSN／Secret 的原值輸出；
- `pg_read_file`、large object、dblink、foreign data wrapper 或 network helper；
- 未知 result section 或未遮罩 identity-bearing column。

允許的 catalog relation 與 function 使用 allowlist，不只依黑名單。

### 3. Sanitized result contract

- 新增空白 CSV／Markdown contract，定義每個 section 的欄位、型別、允許值與預期 cardinality。
- 產出只允許 generic classification，例如 `session_is_superuser`、`session_bypasses_rls`、
  `owner_relation = same/different/unknown`、grant／policy counts與 stable anonymous IDs。
- 提供離線 fixture result，使用明顯虛構值，測試 parser／validator 能接受正常結果並拒絕額外欄位、
  role name、email、URL、DSN、SQL expression 或 application row data。
- 不把 Owner 後續實際結果納入本任務 commit；正式結果須另由 Work 去識別審查。

### 4. Owner Dashboard checklist

文件化需要 Owner 在 Supabase Dashboard 親自確認、但 SQL 無法可靠證明的項目：

- backup／PITR 是否啟用、retention 是否涵蓋預定 window、誰有 restore authority；
- `ntubtob` 是否在 exposed schemas，REST／GraphQL 或其他 client API 是否可達；
- connection pooler／direct connection 的使用方式分類；
- maintenance window 與可接受的 lock／statement timeout。

只記錄 `yes/no/unknown` 與必要的一般分類；禁止 screenshot、帳號、project ref、host、role 名或
其他敏感 metadata 進 repository。

### 5. 使用指引與後續交接

- 提供 Owner 可複製到 SQL Editor 的精確順序、預期輸出 sections、CSV 匯出方式與停止條件。
- 明說「準備 query」不等於「批准執行 query」；Codex 不得代替 Owner 執行。
- 定義 Work 收到結果後如何驗證、去識別、與 TASK-049 fingerprint 比對，及何時退回 blocked。
- 將 TASK-051 merge 事實與 TASK-052 狀態同步到專案文件。

## 明確非目標

- 不連線、查詢或登入 Supabase／production DB／Dashboard／API。
- 不讀取 `.env.yaml`、DSN、Secret、database password 或 provider token。
- 不執行 production SQL，即使是 read-only；執行需 Owner 後續明確批准。
- 不執行 stamp、DDL、backfill、RLS、policy、grant、role、backup、PITR 或 exposed-schema 變更。
- 不建立 production connection tool、Supabase client、psql wrapper 或自動 Dashboard crawler。
- 不決定 RLS 方案、不修改 TASK-051 SQL artifact、不進入 Phase A migration。
- 不 push、PR、merge、部署、通知或修改其他服務。

## 安全要求

- Query 必須 transaction-level read only 並以 rollback 結束；任何無法由 catalog 安全取得的資訊
  記為 Dashboard manual check，不得猜測或擴張權限。
- 所有輸出欄位先做 data minimization；無法證明安全的 identity-bearing value 不輸出。
- SQL 與 validator 使用固定 allowlist，mutation tests 必須證明常見危險語句與敏感輸出會 fail。
- 不以 hashed role ID 宣稱完全匿名；只在同一份結果中供關聯比對，不跨任務追蹤。

## 驗收條件

1. SQL 為單一 read-only transaction，無 DDL／DML／role change／application row read。
2. role／owner／grant／policy／RLS 結果已轉為 generic flags、counts 或匿名關聯，不洩漏名稱與 expression。
3. catalog fingerprint 可偵測 TASK-049 之後的 schema drift與 `alembic_version`／new-table presence。
4. static verifier 與 mutation tests 對所有禁止類別 fail closed。
5. sanitized result validator 能拒絕額外／敏感欄位及不合法 cardinality。
6. Owner 指引清楚分開 SQL Editor 與 Dashboard 手動查驗，包含停止條件。
7. Python 3.10 tests、compile、Black／isort、`git diff --check` 通過。
8. Codex report 明說未連 production、未執行 SQL、未讀 Secret、未 push／PR／merge／部署。

## 建議驗證

```powershell
py -3.10 -m unittest <TASK-052 offline suites> -v
py -3.10 -m compileall -q tools tests
py -3.10 -m black --check <new Python files>
py -3.10 -m isort --profile black --check-only <new Python files>
git diff --check
git status --short
```

本任務不需啟動 Docker；若實作需要 SQL parser，優先使用既有依賴或小型固定 allowlist，不為此
引入大型 dependency。

## 主要預期變更

- `docs/operations/sql/TASK-052-supabase-readonly-access-boundary.sql`
- `docs/operations/data/TASK-052-SUPABASE-ACCESS-INVENTORY.md`
- sanitized result schema／fake fixture
- repository-only verifier／validator 與 tests
- `docs/coordination/reports/TASK-052-CODEX.md`

## 交付與 commit 規則

- 使用描述性 commit，例如：`security(data): prepare sanitized Supabase access inventory`。
- report 與 handoff 優先併入成果或單一 completion commit。
- 完成後更新 `HANDOFF.yaml` 為 `ready_for_review / work`。
- 不得 push、PR、merge 或執行 production query。

## Base commit

`705983b281e60d9f586552e46aab3dd894db5fd2`
