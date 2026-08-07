# TASK-054：確認 Supabase migration 控制面 readiness

## 背景

TASK-049 已保存 production catalog 的去識別化結構證據；TASK-052／053 已確認 catalog fingerprint、
session capability 與固定 33-row access inventory contract。這些 SQL 證據無法證明 Supabase Dashboard
上的 backup／PITR、restore authority、API exposure、連線路徑或 maintenance window，因此 Phase A
migration 仍維持 blocked。

本任務只蒐集 Owner 可在 Dashboard／既有部署設定中人工確認的廣義分類，並由 Work 對照既有 stop
conditions 判讀。不執行 migration，也不改任何 Supabase 或 GCP 設定。

## 目標

- 取得 migration 前 10 項控制面 readiness 的去識別化答案。
- 明確區分已確認、未知與阻塞事項，不以方案名稱或 UI badge 推定可還原性。
- 決定下一步應是補 backup／access evidence、完成 RLS 決策，或準備 Phase A migration 工作包。

## Owner 操作

Owner 僅查看 Supabase Dashboard 與自己已知的維運安排，不按下會儲存或變更設定的按鈕。請把下列
模板複製到對話回覆，只填允許值與必要的一句分類說明：

```text
1. Backup enabled: yes / no / unknown
2. PITR enabled: yes / no / unknown
3. Retention covers migration + verification window: yes / no / unknown
4. Restore authority and procedure available: yes / no / unknown
5. ntubtob listed in exposed schemas: yes / no / unknown
6. REST/GraphQL/client API can reach ntubtob: yes / no / unknown
7. Intended migration connection: direct / transaction-pooler / session-pooler / unknown
8. Current application runtime connection: direct / transaction-pooler / session-pooler / unknown
9. Maintenance window can be agreed before migration: yes / no / unknown
10. Accept 5s lock timeout and 60s statement timeout: yes / no / unknown
```

對第 3、4 項，只有在已知保留範圍涵蓋 migration 與驗證期間，且已知由誰、依何種既有程序可啟動
restore 時才填 `yes`；不需也不得回報人名、日期、project ref 或 URL。

對第 5、6 項，若 Dashboard 顯示 `ntubtob` 為 exposed schema 或可由 Supabase client API 存取，填
`yes`；不要為了測試而發 API request。

對第 7、8 項，只回報連線類型。不得貼 host、port、database、user、password、DSN、connection
string、截圖或環境檔內容。若無法不讀 secret 就判定，填 `unknown`。

## Work 驗收與分類

Work 收到答案後：

1. 僅將允許的 yes/no/unknown／連線類型與去識別化判讀寫入 review。
2. 依既有 stop conditions 分成：
   - `ready`：backup、retention、restore、maintenance、timeout 都明確；API exposure、migration path、
     runtime path 與 RLS 邊界可安全解釋。
   - `needs_evidence`：一或多項為 unknown，但可用唯讀查驗補足。
   - `blocked`：backup/retention/restore 不足，或 API exposure/RLS、pooler compatibility 尚未解決。
3. 不因 SQL Editor session 具高權限，就推定 production runtime connection 或 RLS 行為。
4. 提出唯一下一個最小任務，不同時啟動 migration、RLS 與 application opt-in。

## 非目標與禁止事項

- 不執行 SQL、Alembic、DDL、backfill、restore drill 或 API probe。
- 不連線 production DB，不修改 backup/PITR、exposed schemas、RLS、role、grant 或 connection pooler。
- 不讀取、貼出或提交 `.env.yaml`、DSN、secret、project ref、host、role name 或 screenshot。
- 不部署、push、建立 PR、merge 或發送通知。
- 本任務完成不等於 production migration 獲得批准。

## 驗收條件

1. 10 項答案皆為允許值，未知項目明確保留為 `unknown`。
2. Repository 僅保存去識別化分類與 Work 判讀，不保存原始 Dashboard 證據或連線資訊。
3. Work review 明確列出 stop conditions、可解除項目與下一個最小任務。
4. Phase A migration 在 Owner 另行批准精確工作包前仍維持 blocked。

## 預期文件

- `docs/coordination/reviews/TASK-054-WORK.md`
- `docs/coordination/PROJECT_STATE.md`
- `docs/coordination/HANDOFF.yaml`

## Base commit

`700f7244e15a267054aba1eeca8aec6f603879fa`
