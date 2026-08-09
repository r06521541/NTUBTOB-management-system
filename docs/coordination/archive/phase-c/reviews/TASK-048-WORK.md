# TASK-048 Work review

- 結果：`accepted`
- Branch：`codex/task048-portal-data-foundation`
- 工程 commit：`31844cdaecfd526f36ab4546a732c61021298f95`
- Report/HANDOFF commit：`a1e80d3`
- 驗收日期：2026-08-06（Asia/Taipei）

## 實際查驗

Work 未只採信 Codex 摘要，已檢查實際 branch、commits、working tree、migration、models、
repository/domain、local URL gate、Docker Compose、tests 與完整 diff。

獨立執行結果：

- Docker Compose config：只綁 `127.0.0.1:55432`，使用 local-only database/credentials。
- PostgreSQL 16 container healthy；Alembic current 為 `0002_portal_data_foundation (head)`。
- Persistence tests：32/32 通過（包含實際 PostgreSQL contract/constraints/concurrency）。
- Alembic downgrade → legacy fixture → upgrade head：通過。
- Fake seed 連跑兩次：第一次建立 2、第二次建立 0／重用 2。
- `alembic check`：`No new upgrade operations detected`，migration 與 metadata 無漂移。
- Web Portal：109/109 通過，2 項既有 Windows make/sh skip。
- Game broadcast：28/28；notify cron：9/9；schedule：5/5；LINE webhook：18/18。
- `git diff --check` 通過，working tree clean。
- 驗收 container/network 已移除；專用 volume
  `ntubtob-portal-data-local_portal-data-postgres` 保留供重驗。

## 驗收結論

接受 TASK-048。新 persistence 是 opt-in 且未被現有 production request path 匯入；Person、
Member link、同 provider 多 identities、non-member admin、持久 qualifications、Event publish
snapshot、manual override、team/guest 統計、last-admin lock、audit rollback 與 idempotent backfill
均有真 PostgreSQL 證據。沒有 Supabase、production、Secret、通知、雲端或部署操作。

## 非阻擋限制與後續條件

- 本機沒有可執行的真正 Python 3.10 runtime；目前只有 Python 3.12 執行與 Python 3.10 grammar
  check。進 PR 後應由 hosted Python 3.10 CI 補證據。
- Qualification grant/revoke 目前是低階 repository primitive；接正式 route 前必須新增帶 actor、
  reason、request ID、authorization 與同 transaction audit 的 application service。
- Activity attendance 已有 schema，但尚未建立完整 domain/service contract；接正式 Event UI 前補齊。
- Audit triggers 阻擋 row UPDATE/DELETE，但 production 真正 append-only 還需要 migration role/privilege
  與 TRUNCATE 邊界；目前不得宣稱已具 production-grade audit immutability。
- Local URL gate 能拒絕遠端/Supabase host與錯誤 database name，但不能證明 localhost 後方不是
  tunnel/proxy；production migration 必須使用另立、精確批准且經 inventory 的工作包。
- Legacy baseline 只代表 repository-backed local fixture，絕不是 Supabase production schema 證據。

## Owner 下一步

可批准本 branch push／PR，利用 hosted Python 3.10 CI 補最後 runtime 證據。不得把 PR merge
視為 production migration 或啟用新 persistence；Supabase inventory、migration 與正式接線必須另案。
