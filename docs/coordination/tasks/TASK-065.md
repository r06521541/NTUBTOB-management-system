# TASK-065：設計並離線演練 Phase B Member／Person／LINE identity 回填

## 任務目標

在已完成且尚未接入application的Phase A expand schema上，建立可審查、可重跑、可驗證及可精確回復的
Phase B backfill工作包。先以去識別化唯讀盤點與本機PostgreSQL fixture證明行為，不連線或寫入Supabase
production；正式執行須另立exact execution task並由Owner明確批准。

## 已核准產品規則

1. `members`是永久正式校友名冊；每筆Member可一對一建立Person，不因姓名或display name自動合併。
2. 新回填Person預設為`portal_access_level = 'basic'`、`portal_status = 'inactive'`。
3. Member本身不代表現役或可參賽；**只有已可靠連結LINE identity的Member，才授予active
   `team_player` qualification**。
4. 未連結LINE的Member仍建立Person與`members.person_id`，但不取得`team_player`。
5. 已有明確legacy Member link的LINE user才可自動連至該Member的Person；不得依姓名或其他弱資訊猜測。
6. 未連結且未ignored的LINE user維持pending candidate；legacy `ignored`不自動映射為blocked或disabled，
   只列入去識別化人工判定摘要。
7. 本輪不從runtime admin allowlist提升任何Person；admin/officer與其他qualification須由後續明確、可稽核
   mutation授予。
8. 同一Person可連結同provider多個帳號，但`(provider, provider_subject)`必須全域唯一。

## 使用者價值

- 讓永久校友名冊、Portal登入身份與實際球員資格各自具有清楚語意。
- 保留現有LINE user與Member配對成果，不讓未登入校友被誤列為可出賽球員。
- 在正式寫入前，以可重現證據驗證筆數、映射、稽核、重跑與rollback。

## 實作範圍

### A. 去識別化 production 唯讀盤點包

建立固定SQL與strict validator，輸出只能是section／metric／status／boolean／integer／generic text，不得輸出
Member姓名、LINE user id、display name、provider subject或其他個資。至少驗證：

- Phase A revision及13張portal tables仍符合zero-row、RLS enabled／zero-policy boundary；
- Member總數、`person_id`已連結／未連結／orphan／collision counts；
- legacy LINE users總數、linked-member、unlinked non-ignored、ignored counts；
- LINE user連到不存在Member、同一LINE subject重複、同一Member多個LINE accounts等分類counts；
- new Person、auth identity、qualification及audit tables目前application row counts；
- 形成backfill預期筆數，但不輸出實際identity或Member ID。

SQL僅供Owner日後在Supabase SQL Editor手動執行；本任務不得自行連線production或要求credential。

### B. Deterministic backfill artifact

建立由固定input contract產生或驗證的transactional SQL/artifact，至少遵守：

- fail closed preconditions：revision、new-table zero state、legacy linkage與expected counts必須與批准證據一致；
- transaction-local bounded lock/statement timeout，並以advisory transaction lock避免並行執行；
- 依Member ID穩定排序建立Person並回填`members.person_id`；不以姓名比對；
- 只為legacy LINE user已有有效Member link者建立LINE auth identity；provider subject必須完整保留在DB但不得出現在
  evidence/log；
- 只有上述已可靠連結LINE identity的Member取得active `team_player`；
- 建立可去重的audit record，reason不得沿用`local legacy member backfill rehearsal`；
- 重跑不得新增Person、identity、qualification或audit，也不得重複變更version；
- 任一constraint、count、identity collision、orphan或audit失敗，整個transaction rollback。

不得把正式Member IDs、LINE IDs、admin allowlist或production row values寫入repository。

### C. Rollback與post-check

提供與該batch可精確對應的rollback設計及唯讀post-check：

- post-check驗證Person/member link、LINE identity、`team_player`與audit數量及引用完整性；
- 驗證沒有admin/officer、非LINE identity或未連LINE Member的`team_player`；
- 驗證legacy LINE／Member／attendance／game資料除`members.person_id`外未改動；
- rollback只能移除本batch建立的audit、qualification、identity與Person，並清空對應`members.person_id`；
- rollback不得刪除或改寫legacy Member、LINE user、game或attendance資料；
- application一旦開始讀寫新模型，rollback即失效，必須在Phase C前清楚標記boundary。

### D. 本機 PostgreSQL 演練與測試

使用明顯虛構fixture，在repository支援的PostgreSQL版本離線驗證：

- 有LINE／無LINE Member、同Member多LINE accounts、unlinked、ignored、orphan與collision；
-正確Person status/access、identity mapping及條件式`team_player`授予；
- transaction atomicity、advisory-lock concurrency、timeout、idempotent rerun與audit uniqueness；
- precondition drift與任何collision均fail closed；
- rollback回到exact pre-backfill state，第二次rollback不得破壞資料；
- evidence不包含fixture名稱、subject或raw row values。

既有`backfill_members(fake_admin_member_ids=...)`目前是local rehearsal。可最小調整或另建production artifact，但不得
讓既有fake demo行為誤成正式政策；所有直接caller與測試必須一併盤點。

## 非目標

- 不連線、查詢或寫入Supabase production，不執行DML/backfill/rollback。
- 不執行Phase C runtime grants、RLS policies、application dual-read/write、Web/LINE route接線或deployment。
- 不建立admin/officer、不讀`WEB_PORTAL_ADMIN_MEMBER_IDS`或任何env/Secret。
- 不自動處置ignored identity、不以姓名匹配、不回填event/attendance。
- 不修改legacy資料語意、正式schema、IAM、Scheduler、Cloud Run/Functions或通知行為。

## 驗收條件

1. 產品規則以contract tests固定，未連LINE Member不會取得`team_player`。
2. 唯讀inventory與post-check輸出完全去識別化，strict validator拒絕缺列、重複、未知或不符結果。
3. Backfill在local PostgreSQL一次成功、第二次無變更，錯誤時atomic rollback。
4. 同一Person可有同provider多identity，重複provider subject及弱資訊自動合併均被拒絕。
5. Rollback可回到exact pre-state，且明確記錄何時因Phase C開始而不可再使用。
6. Python 3.10相容；不需外部API、production DB或secret即可完成全部測試。
7. Codex report明確區分已證明的local行為與尚未執行的production inventory/backfill。

## 建議驗證命令

Codex應依實際新增工具補上精確命令，至少執行：

```powershell
python -m unittest discover -s shared_lib/tests -v
python -m compileall -q shared_lib tools
git diff --check
git status --short
```

若PostgreSQL integration tests使用既有Docker wrapper，必須採ephemeral、無production credential、無persistent
volume並有ownership-guarded cleanup；Windows缺少Unix `make/sh`時使用等價Python/PowerShell入口，不修改Makefile。

## 停止條件

- 發現Phase A production schema或legacy linkage與既有證據衝突。
- 無法在不輸出個資／identity的前提下形成可驗證證據。
- 需要決定ignored identity、admin promotion或不可靠identity matching。
- 需要production credential、DDL/DML、Secret、deployment、通知或任何外部變更。

## 交付物

- 固定唯讀inventory SQL、schema與strict validator。
- Deterministic backfill、post-check與rollback artifacts及checksum/verification方式。
- Local PostgreSQL fixtures、contract/integration tests與操作文件。
- `docs/coordination/reports/TASK-065-CODEX.md`及更新後handoff。

## Base commit

`d33a42a9219f33a2bc191deba910de986fcb027e`
