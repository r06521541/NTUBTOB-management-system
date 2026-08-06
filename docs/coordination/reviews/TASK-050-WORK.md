# TASK-050 Work 驗收

## 結論

`changes_requested`。本機 exact-schema rehearsal、migration chain 與測試均通過，但 Alembic metadata 尚未完整表達 legacy schema 的所有權邊界；目前執行 `alembic check` 會產生可能刪除既有 production legacy 結構的操作，因此本任務尚不能視為 migration-ready。

## 查驗基準

- Implementation commit：`d2b7b848289d702b4c166f61a576ccb516c79555`
- Completion commit：`b2218ced1196ca6fa96ee7cc43be85a0a6119528`
- Codex report：`docs/coordination/reports/TASK-050-CODEX.md`
- Work 直接檢查實際 diff、migration、models、fixture 與 tests，未只依賴完工摘要。

## 通過項目

- Python 3.10.7：35 項 portal-data tests 全數通過。
- Python 3.12.13：35 項 portal-data tests 全數通過。
- `compileall`、Python 3.10 AST grammar check、`git diff --check` 通過。
- local PostgreSQL migration downgrade／fixture rebuild／upgrade chain 通過。
- Docker Compose 指向 local `127.0.0.1:55432`、local database 與 named volume；驗收後 container 已停止，未連 Supabase。
- attendance current-state projection 以 `(updated_at, id)` 決定最新紀錄，符合 TASK-049 證據。

## 阻擋問題

`py -3.10 -m alembic check` 回報 `New upgrade operations detected`：

- 建議刪除 8 張未被 metadata 管理的 legacy tables：`line_notify_tokens`、`discord_webhooks`、`ballparks`、`game_attendance_replies`、`line_groups`、`attendance_reply_types`、`line_users`、`cancellations`。
- 建議刪除 `members.major`、`positions`、`enroll_year`、`number`。
- 建議把 production-compatible `games` SMALLINT／timezone-aware／nullable 欄位改回 Integer／timezone-naive／NOT NULL。
- 建議移除 `members.id` 與 `games.id` 的 identity metadata。

根因是 `PortalDataBase.metadata` 尚未完整建模 legacy schema，且 Alembic env 沒有明確、可測試的 object ownership filter。若未先處理，後續 autogenerate 可能產生破壞性 DDL。

## 必要修正

1. 將 `LegacyMemberRecord`、`LegacyGameRecord` 補齊 TASK-049 catalog 已確認的 identity、欄位、型別、nullable 與 timezone metadata。
2. 對另外 8 張 legacy tables 採用完整 read-only model，或在 Alembic 加入明確且有測試的 `include_object`／ownership boundary，確保不會產生 drop legacy object 的 migration。
3. 新增 regression test，執行 Alembic metadata check 並要求沒有新 upgrade operations。
4. 重跑 Python 3.10 tests、compile/import、migration chain、`alembic check` 與 `git diff --check`。
5. 不擴張到 `ignored` mapping、RLS policies、production DDL／stamp／backfill 或正式環境。

## 非阻擋觀察

- `project_current_attendance` 可接受 `member_id=None`；TASK-049 已確認 production null count 為零，本輪不要求調整。
- Codex report 所述 Windows 全域 Python 限制不是程式相容性失敗；Work 已用 Python 3.10.7 實跑通過。

## 交棒

請 Codex 依上述必要修正補正同一任務，再交回 Work 驗收。
