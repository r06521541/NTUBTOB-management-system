# TASK-048 Codex report

## 結果

狀態：`ready_for_review`

已完成 opt-in、local-only 的 Person／Portal access／Auth Identity／Qualification／
Event persistence foundation。現有 Web Portal、LINE、webhook、排程服務與 legacy models
沒有匯入或啟用這條新 persistence path；未連 Supabase production、未讀 secret、未通知、
未操作雲端、未 push／PR／merge／deploy。

- Base commit：`64f2dca`
- 任務規格 branch 起點：`a7b7cc4`
- 工程 commit：`31844cdaecfd526f36ab4546a732c61021298f95`
- Branch：`codex/task048-portal-data-foundation`

## 實際完成內容

1. 新增 Alembic `legacy baseline` 與單一 expand revision；baseline 明確為 no-op，production
   必須先 inventory／另案批准後才能 stamp。
2. 新增只綁定 `127.0.0.1` 的 PostgreSQL 16 Compose 環境、明顯 local-only database／
   credentials 與專用 named volume。
3. 所有 migration、seed、integration command 都必須通過 local database URL gate；remote、
   未知 database 與 Supabase URL 在建立連線前拒絕。
4. 新增獨立、未掛入 legacy model registry 的 SQLAlchemy 2.0 models：People、Member nullable
   Person link、Auth Identity、Qualification、append-only access audit、Event／Activity、eligibility、
   invitee override/snapshot、兩層 attendance、manager 與 Event audit。
5. 使用 text + CHECK、FK、unique、partial indexes、`timestamptz` 及 audit update/delete triggers；
   沒有 PostgreSQL enum，也沒有 token/provider payload/cookie/LINE profile 欄位。
6. 新增小型 domain types/service boundary、單一 in-memory repository 與 PostgreSQL adapter。
7. 完成 identity 核可／blocked、non-member admin、同 provider 多帳號、access/status mutation、
   qualification 有效期／撤銷、last-admin advisory lock、audit atomicity、Event publish snapshot、
   manual include/exclude、attendance 與 team/guest roster 分流。
8. 完成 legacy Member local backfill 與 fake seed；重跑不重複 Person、qualification、identity
   或 audit，也不以姓名自動合併。
9. 新增 Windows／Unix local 操作、migration rehearsal、測試、停止 container 與僅刪除此
   Compose named volume的文件。

## 測試與驗證

實際執行並通過：

- `docker compose -f docker-compose.portal-data.yml config`：通過；host bind 為
  `127.0.0.1:55432`。
- `docker compose ... up -d portal-postgres`／`ps`：PostgreSQL 16.4 container healthy。
- `python -m tools.setup_portal_data_legacy` → Alembic stamp baseline → upgrade head：通過。
- Alembic `downgrade 0001_legacy_baseline` → fixture rerun → `upgrade head`：通過。
- fake seed 連續兩次：第一次 `created=2`，第二次 `created=0/reused=2`。
- local/Supabase URL fail-closed 命令：遠端 fake Supabase URL 在連線前拒絕。
- `python -m unittest discover -s tests/portal_data -v`：32/32 通過，in-memory 與實際
  PostgreSQL contract 同時執行。
- `python -m unittest discover -s apps/web_portal/tests -v`：109/109 通過，2 項既有 Windows
  `make`／`sh` platform skip。
- 其他回歸 suites：game broadcast 28/28、notify cron 9/9、schedule 5/5、LINE webhook
  18/18、deployment tools 41/41 通過。
- Black 24.4.2 check：15 個新 Python 檔通過。
- `compileall`：apps、functions、shared library、migrations、tools、portal-data tests 通過。
- Python 3.10 AST grammar：15 個新 Python 檔通過。
- shared library final source 建 wheel、安裝並從 repository 外 import：通過。
- `git diff --cached --check`、最後 `git diff --check`：通過。

## Environment 狀態

- 本任務啟動的 container 與 Compose network 已停止／移除。
- 保留專用 named volume：`ntubtob-portal-data-local_portal-data-postgres`，方便 Work
  重驗；文件提供精確 `docker compose ... down -v` 清除方式。
- PostgreSQL image 保留於本機 Docker cache，未刪除其他 image／container／volume。
- Alembic、psycopg2-binary、Black、isort 僅安裝於 Codex bundled Python。

## 未驗證與風險

- Windows Store 的 `py -3.10` executable 目前無法啟動，因此本輪沒有真正 Python 3.10
  interpreter 或 hosted runner 證據；只有 Python 3.12 execution 加 Python 3.10 grammar check。
- 未盤點 Supabase production 的真實 tables、columns、constraints、row volume、locks、orphans、
  duplicate candidates 或 migration state；`0001` fixture 不能視為 production schema。
- 未執行任何 production stamp／DDL／backfill；expand migration 的 production lock time、
  `NOT VALID`／分段 validate 與 rollout順序仍需在正式工作包另行設計與批准。
- 新 persistence 尚未接 Web Portal principal/session、現行 Member/LineUser、legacy Game attendance、
  crawler、通知或 UI；現有 production 行為完全不變。
- `team_player` 正式回填權威來源、敏感欄位可見性、通知／發布核可與 blocked 復原仍是產品待決事項。
- Local destructive downgrade 只適用隔離 database；production rollback 原則仍是保留 expand
  schema並回退相容 application。

## 變更檔案

- Root/local tooling：`README.md`、`alembic.ini`、`docker-compose.portal-data.yml`、
  `requirements-migrations.txt`
- Migrations：`migrations/README.md`、`migrations/env.py`、`migrations/script.py.mako`、
  `migrations/versions/0001_legacy_baseline.py`、
  `migrations/versions/0002_portal_data_foundation.py`
- Persistence package：`shared_lib/shared_module/portal_data/__init__.py`、`domain.py`、
  `fixtures.py`、`local_database.py`、`models.py`、`repository.py`、`services.py`
- Local tools：`tools/setup_portal_data_legacy.py`、`tools/seed_portal_data_fake.py`
- Tests：`tests/portal_data/test_local_database.py`、`test_postgres_constraints.py`、
  `test_repository_contract.py`
- Docs：`docs/README.md`、`docs/development/LOCAL_PORTAL_DATA.md`、
  `docs/planning/EVENT_MANAGEMENT_PLAN.md`、`ROLE_PERSISTENCE_PLAN.md`、
  `WEB_PORTAL_ACCESS_MATRIX.md`

## 需要 Owner 決策

本輪只需 Work 驗收，不需要立即 production 決策。若後續要接 Supabase 或 production request
path，必須另立任務並取得 production inventory、exact migration、backfill、rollback、Secret／
deployment 範圍的明確批准。
