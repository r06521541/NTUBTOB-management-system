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

## 執行前工具缺口與 prerequisite

Local path preflight 已確認 destination 空白、約 14.9 GB 可用、env-file 存在且非空、Git clean、固定
image digest 正確，三個 planned artifact paths 亦通過 verifier。但 Windows host 沒有 `pg_restore`，
現有 TASK-055 verifier 無法在 Docker-produced archive 上執行 `create/verify`。Production dump 在此缺口
解除前不得開始。

Codex 必須先為 verifier 增加固定且 fail-closed 的 Docker inspection backend：

- 只允許既有固定 image ID
  `sha256:89ec47deeeddac28eb60b5672a456c54213ff4528f8752fda7f7c2a0e4ead36a`，不得接受任意 image、
  tag、registry 或 pull；
- 只可執行 container 內 `pg_restore --list <mounted-archive>`／`pg_restore --version`；
- `docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges`，archive parent
  只讀 bind mount；不得 mount repository、env-file、home 或 Docker socket；
- 不傳 `--env-file`、`-e`、host environment、credential、database/network options；
- 使用 argument list、timeout、captured output、`shell=False`，錯誤不得回顯 listing、paths、Docker output
  或 environment；
- CLI 必須由明確 backend option 啟用，default host behavior 保持相容；preflight 不啟動 Docker；
- tests mock subprocess，驗證 exact security flags、fixed image、read-only mount、allowed commands，以及拒絕
  arbitrary backend/image/options、timeout/nonzero/output leakage；
- 不得增加 `pg_dump`、restore、SQL、connection、delete、overwrite 或 network 能力。

完成 Python 3.10 CI、Work review、push／PR／merge 後，才回到本文件列最終 production dump 命令。

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

1. 唯讀確認 Git clean／exact merged commit、Docker image digest、destination 在 repository 外、三個 artifact
   path 不存在，並執行 verifier `preflight`。
2. 以固定 image ID 啟動一次性 `docker run --rm` client：
   - 只 mount approved destination 到 container `/backup`；
   - 只以 `--env-file` 傳入 PostgreSQL standard variables；
   - 不 echo／inspect env-file，不記錄 Docker inspect environment；
   - 執行 custom format、`--schema=ntubtob`、`--no-owner`、`--no-privileges`、
     `--lock-wait-timeout=5000`、固定 `/backup/<approved-basename>.dump`；
   - 不使用 transaction pooler、不輸出 archive 至 stdout、不 overwrite、不 retry 變更 options。
3. 僅在 dump exit zero 後，以 TASK-055 verifier 的固定 Docker inspection backend 建立 manifest/checksum，
   再對 retained copy 執行 verify。
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

## Production attempt evidence and required compatibility fix

- Direct-connection attempt failed with output suppressed and produced only a 0-byte artifact; Owner approved deletion
  of that exact empty file. No retry occurred under the direct approval.
- Owner changed the private env-file to session-pooler and approved one new attempt. The production schema-scoped
  custom archive completed successfully at 56,903 bytes.
- Docker verifier `create` then failed closed before sidecar creation with generic category
  `archive TOC failed the sanitized-content contract`; archive is retained, manifest/checksum are absent, and no dump
  retry, cleanup, restore or migration occurred.
- Repository sanitized catalog already contains the legitimate table identifier `line_notify_tokens`. The current
  sensitive regex treats the identifier substring `token` as a secret token, so this is the primary reproducible
  compatibility hypothesis; Codex must not inspect the production archive or listing.

Codex must add a regression using only conspicuously fake TOC metadata and repository-known identifier
`line_notify_tokens`, then narrow `password`／`secret`／`token` detection to standalone sensitive terms rather than
valid identifier substrings. Tests must still reject standalone token/secret/password values, URLs/DSNs, SQL injection,
foreign schemas and arbitrary TOC lines. Do not special-case an unreviewed production listing or remove the overall
sensitive scan. After Work review and Python 3.10 CI/merge, re-verifying the retained production archive requires a new
Owner approval; production dump must not be repeated.

## Base commit

`84c20dbbab6c6134fcd1a3d010aefc154aa93e22`

## Closeout

- Production schema-scoped custom archive 已建立並保留；Docker verifier compatibility 修正經 PR #60 的
  Python 3.10 CI 通過，squash merge commit 為 `d8ec8b175ff3f7106fcad978e93970714afabdca`。
- Owner 另行批准後，既有 archive 的 sanitized manifest/checksum `create` 與獨立 `verify` 均通過。
- Sanitized evidence：56,903 bytes、PostgreSQL client major 16、custom format、`ntubtob` schema scope、
  listing verified；完整 hash 與 timestamp 記錄於 Work review。
- 未重跑 dump、未 restore、未執行 migration、未連線 production DB、未讀 credential env-file。
- TASK-056 完成；下一階段 isolated restore rehearsal／migration gate 必須另開任務並重新取得授權。
