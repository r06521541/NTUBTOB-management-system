# TASK-047 Codex report

## 結果

完成 Web Portal 正式角色與多類型 Event 持久化的 repository 盤點與一體化設計文件。未修改程式或 models/schema，未連 production DB、讀取 secrets、發通知或操作雲端資源。

## 已查證事實

- Production principal 目前只可能是 member 或 `WEB_PORTAL_ADMIN_MEMBER_IDS` 命中的 admin；沒有 officer 正式來源。
- Production session 保存 `user_id`／`member_id`，role 不在 session；現有 route guards 使用集中 capability policy。
- Member model 目前只有 `id`／`name`；LineUser 的 `member_id` 是身分配對，`ignored` 不是 Member 帳號狀態。
- Demo 三角色與 Event Builder 均為 development-only session prototype。
- 正式 models 只有既有 Game／game attendance，沒有 Event/Activity；repository 沒有 migration framework。

## 設計成果

- Owner 後續核准 Person 為自然人與授權主體；Member 是 0..1 關聯的永久正式校友名冊。先前將 role/status 直接放 Member 的方案已被取代。
- Access level 改稱 `basic`／`officer`／`admin`；status 是 pending/active/disabled/inactive/blocked；team_player/guest_player/affiliate/staff 是獨立多值 qualifications。
- Auth identities 多對一 Person，同 provider 可綁多帳號；pending identity 由 admin 匹配、建立 non-member Person 或 blocked。
- Event publish 依 qualification 規則產生 invitee snapshot，支援 audited individual override；attendance/roster/statistics 區分 team 與 guest players。
- 提供 expand、dual-read、backfill、受控寫入、contract 與 rollback 階段；明確指出使用限制狀態後不可回滾至不理解 Person status 的 revision。
- Local prototype 建議使用單一 in-memory repository + fixtures，不逐表 mock；正式 persistence 以 ephemeral PostgreSQL/Supabase local integration 驗證 migration、constraints、transaction 與 concurrency。
- 規劃 allowlist bootstrap/break-glass、last-admin 防護、audit 原子性及後續可獨立驗收 slices。

## 驗證

- 使用 `rg` 盤點 role/capability、admin allowlist、session identity、Demo roles/Event routes、Member/LineUser/Game models 與測試 callers。
- 本任務只有文件變更，依 Owner 指示不執行 Web Portal tests；沒有宣稱 runtime 行為已改變或通過整合驗證。
- `git diff --check` 與 `git status --short` 在 commit 前執行並記錄。

## 變更檔案

- `docs/planning/ROLE_PERSISTENCE_PLAN.md`
- `docs/planning/ROLE_ACCESS_PROPOSAL.md`
- `docs/planning/EVENT_MANAGEMENT_PLAN.md`
- `docs/planning/WEB_PORTAL_ACCESS_MATRIX.md`
- `docs/coordination/reports/TASK-047-CODEX.md`
- `docs/coordination/HANDOFF.yaml`

## 尚待 Owner 決策

- 未回覆姓名、正式通知/發布核可、敏感 Person 欄位可見性、inactive/blocked 復原流程與 team_player 回填權威來源。
- Migration 工具、ephemeral integration runtime 與任何正式 rollout 均需另案批准。

## Owner 決策修訂

本 report 後續以同一 TASK-047 文件修訂 commit 記錄 Owner 核准模型；此次修訂未修改 `HANDOFF.yaml`，避免與 Work 的交棒／驗收狀態衝突。
