# TASK-056：核准一次 production logical backup 執行包

## 背景

TASK-055 已完成 repository-only verifier、runbook 與 isolated PostgreSQL 16.4 fake dump/list/restore
驗證；PR #58 的 Python 3.10 CI 已通過並 squash merge 至
`84c20dbbab6c6134fcd1a3d010aefc154aa93e22`。Production 目前沒有 provider backup／PITR，故
Phase A migration 在建立並驗證 production logical archive 前維持 blocked。

本任務是 production data operation 的精確批准閘門。Work 只能在 Owner 回覆本文件要求的非敏感
選項，並再次批准完整範圍後，執行一次 schema-scoped `pg_dump`。本文件建立本身不授權連線、dump、
archive handling、restore 或 migration。

## 已確認執行基準

- Source code／runbook commit：`84c20dbbab6c6134fcd1a3d010aefc154aa93e22`。
- Production PostgreSQL server major：`15`（TASK-052 sanitized inventory）。
- Windows host 沒有可直接呼叫的 `pg_dump`／`pg_restore`。
- Local Docker engine 已有 `postgres:16.4-alpine` image，image ID：
  `sha256:89ec47deeeddac28eb60b5672a456c54213ff4528f8752fda7f7c2a0e4ead36a`。
- PostgreSQL 16 `pg_dump` 可 dump PostgreSQL 15；仍須在執行時記錄 generic client/server major match。
- Current runtime 使用 session pooler；backup connection 優先 direct，若 direct 在 operator network 不可達，
  只能停下並另行 review session-pooler，不得自行改用 transaction pooler。

## Owner 必須先提供的非敏感選項

只回覆分類，不貼任何 path 內容以外的 connection metadata：

```text
1. Destination directory prepared: yes / no
2. Destination is encrypted and not cloud-synced/shared: yes / no / unknown
3. Credential env-file prepared outside repository: yes / no
4. Credential env-file contains only PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD: yes / no / unknown
5. Connection class in that file: direct / session-pooler / transaction-pooler / unknown
6. Approved execution window (Asia/Taipei): YYYY-MM-DD HH:MM–HH:MM
7. Normal user replies may continue during backup: yes / no
8. No deployment/schema/migration work will overlap: yes / no
```

Owner 可私下告知 Work exact destination directory 與 env-file path 供命令使用，但不得貼檔案內容、DSN、
host、port、database、user、password、project ref 或 screenshot。Work 不得開啟 env-file；只可把 path 交給
Docker `--env-file`。

## 預定精確操作邊界

在 Owner 完成上述選項並另行批准後，Work 才可：

1. 唯讀確認 Git clean／exact commit、Docker image digest、destination 在 repository 外、三個 artifact
   path 不存在，並執行 verifier `preflight`。
2. 以固定 image ID 啟動一次性 `docker run --rm` client：
   - 只 mount approved destination 到 container `/backup`；
   - 只以 `--env-file` 傳入 PostgreSQL standard variables；
   - 不 echo／inspect env-file，不記錄 Docker inspect environment；
   - 執行 custom format、`--schema=ntubtob`、`--no-owner`、`--no-privileges`、
     `--lock-wait-timeout=5000`、固定 `/backup/<approved-basename>.dump`；
   - 不使用 transaction pooler、不輸出 archive 至 stdout、不 overwrite、不 retry 變更 options。
3. 僅在 dump exit zero 後，以 TASK-055 verifier 建立 manifest/checksum，再對 retained copy執行 verify。
4. 回報 sanitized evidence：basename、byte size、SHA-256、UTC timestamp、client major、pass/fail；不回報
   listing、connection identity 或 row data。
5. 不開啟 archive、不 restore、不 migration、不刪除任何 artifact。

## 對線上使用者的影響

`pg_dump` 使用一致性 snapshot，通常不阻擋一般 INSERT／UPDATE／出席回覆；它會取得讀取用 lock 並阻擋
衝突的 DDL。Backup window 不需要主動阻擋隊友，但必須禁止同時 deployment、schema migration、manual
DDL 或其他 database maintenance。若 lock wait、connection 或 output 有任何歧義，立即停止且不進入
Phase A。

## Stop conditions

- 任一 Owner 答案為 `no/unknown`，connection 不是 `direct`，或 exact paths 尚未確認。
- Docker image digest、server/client compatibility、Git commit 或 runbook drift。
- Destination 在 repository、symlink/reparse、雲端同步、shared/removable 未受控位置，或未確認加密。
- Env-file 被 Work 讀取／輸出，欄位超出 allowlist，或 credential 出現在 argv/log/screenshot。
- Artifact path 已存在、disk 不足、dump nonzero、lock timeout、listing/manifest/checksum validation fail。
- 任何 concurrent deployment、schema work、migration 或 production incident。

Stop 後不得刪除或 overwrite partial／ambiguous artifact；隔離 exact path，另行取得 cleanup approval。

## 明確未授權

- 目前不授權讀 env-file、連 Supabase、production `pg_dump` 或任何 SQL/API。
- 不授權 production restore、isolated restore with production data、migration、maintenance mode 或 deployment。
- 不授權 Secret Manager、IAM、Cloud Run、Function、Scheduler、RLS、grant、role、backup/PITR 設定變更。
- 不授權刪除、上傳、同步、commit 或分享 archive／manifest／checksum。
- 不授權 push、PR 或 merge 本 task 文件，除非 Owner 另行要求。

## 完成定義

TASK-056 只有在以下皆完成才可結案：

1. Owner 的 8 項分類與 exact path 已安全確認。
2. Owner 批准 Work 所列出的最終完整命令與時間窗。
3. Production dump exit zero，artifact verifier create/verify 通過。
4. Sanitized evidence review 完成；archive 留在 approved encrypted location。
5. Phase A 仍未執行，下一步另開 isolated restore rehearsal／maintenance gate。

## Base commit

`84c20dbbab6c6134fcd1a3d010aefc154aa93e22`
