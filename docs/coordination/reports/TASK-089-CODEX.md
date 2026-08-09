# TASK-089 Codex report

## Result

- 新增獨立 Person 管理 route：`/manage/people` 支援搜尋／分頁，`/manage/people/<person_id>` 提供第二層詳情／編輯；既有 `/match-member` legacy route 保持相容。
- 新增獨立 pending identity route：`/manage/pending-identities`，不與 Person 列表混用；URL 不綁定角色名稱，權限仍由 capability policy 控制。
- 新增既有 Member 名冊建立 Person 的 transactional repository contract，含 active/basic 初始狀態、team_player 初始資格、重複衝突拒絕與 audit request-id。
- 新增集中式 portal 文案 `ui_text.py`，account／attendance 使用「平台」與「暱稱」標籤。
- 補正新管理頁全部使用集中式 `PORTAL_COPY`（含 Person／Member／pending identity labels），template contract test 確認不再輸出「顯示名稱」。
- 新增 route/template 與 repository 變更；未執行 production、部署、Secret、正式資料或真實通知操作。

## Verification

- `C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s apps/web_portal/tests -v`：128 tests passed，2 tests skipped（環境缺少 make/sh）。
- `C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile apps/web_portal/app.py apps/web_portal/ui_text.py shared_lib/shared_module/portal_data/identity_lifecycle.py`：通過。
- `git diff --check`：通過。

## Handoff

Implementation commit：`c8759c19618e09e63b3ce9815029b108cb05715e`；已 push `origin/codex/phase-d-identity-admin-operations`。
HANDOFF 已交回 `ready_for_review/work`。未驗證：非 production browser/LINE in-app manual smoke 尚未實際執行。
