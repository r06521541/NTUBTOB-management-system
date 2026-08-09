# TASK-067：執行 Production Phase B identity backfill

## 任務目標

在Owner一次性條件批准下，以TASK-066已驗證的去識別aggregate evidence產生之exact rendered SQL，在30分鐘
bounded window內依序完成fresh read-only inventory、單一transaction Phase B backfill與read-only post-check。
任一gate失敗即停止；本任務不包含Phase C application rollout、deployment或任何ad-hoc修補。

## Exact source與artifacts

- Repository source commit：`8f40278bdbdabc0876ededba77264fa1016fd04b`
- Current package commit：建立本文件的merge/main commit；不得改變下列既有SQL artifacts。
- Fresh inventory：`docs/operations/sql/TASK-065-phase-b-inventory.sql`
  - SHA-256：`ee83a89a5b8e7548d78d3e26cbf3efc0c3d95f17fda067bb94be66afae45f9e5`
- Backfill template：`docs/operations/sql/TASK-065-phase-b-backfill.sql`
  - SHA-256：`ff8327c2470136cf5fffe8c1dc96853ac732e0b16749a5cb6344d07b8079b9a7`
- Rendered execution artifact（repository外，Owner Downloads）：
  - `TASK-067-phase-b-backfill-rendered.sql`
  - 8,853 bytes
  - SHA-256：`3f9f884423680223c882bd13e7c819a0ff8f9071b05d420274ba4c3cdbe8c831`
  - 相鄰sidecar：`TASK-067-phase-b-backfill-rendered.sql.sha256`
  - exactly one `BEGIN;`／`COMMIT;`，0 unresolved placeholders。
- Post-check：`docs/operations/sql/TASK-065-phase-b-postcheck.sql`
  - SHA-256：`297e9e16bef8831604689752a1f8c974a6891e72f38cc4bb5ac75a679a77e0e6`
- Approved TASK-066 CSV SHA-256：`a11d789d7acc1eefa4373ba19f071c420e4e6f37c74a04cb82dad027fa032210`

不得修改、格式化、另存成不同encoding、拆句、手動代換count或重建rendered artifact。任一byte checksum不符即停止。

## 預期效果

- 建立197個`basic/inactive` People並一對一回填197個`members.person_id`。
- 為56個reliable non-ignored LINE links建立56個linked LINE auth identities。
- 為其對應的56位distinct Members授予56個active `team_player` qualifications。
- 建立197 member、56 identity及56 qualification audits，總計309筆append-only access audit。
- 4個unlinked non-ignored及5個ignored LINE users維持原狀。
- 不建立admin/officer，不處理event/attendance，不依姓名匹配。

## Window與freeze

- Window由Owner批准後第一次fresh inventory開始，最長30分鐘；中斷、跨操作時段或狀態不明即失效。
- 維持TASK-066起的Member配對、ignored／LINE user維護及portal schema／RLS／policy／trigger freeze。
- Window內不部署、不啟動Phase C、不執行其他manual SQL或portal-data維護。
- 一般legacy game、attendance與既有服務可繼續，因execution gate不綁定其counts；不得為本任務人工invoke通知。

## Owner批准後的精確順序

### 0. Work local preflight

1. 確認main/origin main、working tree、source ancestry與四個artifact checksums。
2. Strict validate原TASK-066 CSV並確認其SHA-256。
3. 驗證rendered artifact為8,853 bytes、單一BEGIN/COMMIT、0 placeholders且checksum一致。
4. 執行`python -m tools.portal_data_phase_b verify`。任一失敗即停止。

### 1. Owner fresh production inventory

1. 在Supabase SQL Editor新query完整執行exact inventory SQL一次。
2. 匯出唯一六欄CSV，不修改，交給Work。
3. Work strict validate並要求所有metrics與TASK-066 approved CSV逐項完全相同。任何count、revision、RLS、policy、
   trigger或zero-row drift即停止，不執行backfill。

### 2. Owner production backfill

只有Work在同一window明確回覆fresh inventory與approved evidence完全一致後：

1. 在新的Supabase SQL Editor query，從repository外exact rendered artifact完整複製，不從template自行render。
2. 最後核對檔名、8,853 bytes、SHA-256、單一BEGIN／COMMIT及transaction-local 5秒lock／60秒statement timeout。
3. 執行exactly once。不得人工重送個別statement或重新render。
4. 若明確error、timeout或transaction rollback，停止並保留generic error category；不得直接重跑。

### 3. Owner production post-check

1. Backfill顯示成功後立即在新的query執行exact post-check SQL一次。
2. 匯出唯一六欄CSV，不修改，交給Work。
3. Work strict validate並以`tools.portal_data_phase_b compare`比較fresh inventory／post-check。全部通過才宣告成功。

## 成功條件

- 197 People/member links、56 LINE identities、56 team_player、309 audits exactly成立。
- 所有People為basic/inactive；沒有admin/officer、ignored identity或無LINE team_player。
- Audit action、request ID及target relationships一致，無unexpected audit。
- Phase A revision、13 tables、13 RLS enabled、0 forced、0 policies及其他portal zero rows不變。
- 未修改legacy LINE rows、Member資料（除`person_id`）、game/attendance或runtime服務。

## 失敗與狀態不明

- Commit前錯誤：單一transaction應完整rollback；以fresh inventory確認仍為zero-row pre-state後停止。
- Connection loss／執行結果不明：**不得重跑backfill**。先執行exact post-check一次：
  - strict post/compare通過，視為已commit；
  - post-check不符時，再執行exact inventory一次；若strict inventory與approved evidence完全相同，視為已rollback；
  - 兩者皆不通過，凍結Phase B/C並交回Owner另案決策。
- Commit後semantic error：保留People／identity／qualification與append-only audit，不停用trigger、不DELETE audit、不宣稱
  exact rollback；另立forward compensation task與精確批准。
- Logical backup不作為一般post-check finding的自動restore手段；restore需要全新批准。

## 明確未授權

- 未經本TASK精確批准，不執行fresh inventory、backfill或post-check。
- 不執行ad-hoc SQL、個別statement retry、DELETE/TRUNCATE/drop、trigger disable、downgrade或restore。
- 不啟動Phase C、RLS policies/runtime grants、Web/LINE接線或deployment。
- 不修改Secret／IAM／Scheduler／cloud resources，不發送LINE／Discord通知，不人工invoke服務。

## Owner批准文字

> 批准TASK-067：依文件固定的source commit、TASK-066 evidence hash、四份SQL/artifact checksum、8,853-byte
> repository外rendered artifact、30分鐘window與freeze boundary，執行一次fresh read-only inventory；僅在Work確認
> 與approved evidence逐項完全一致後，執行exactly once Phase B backfill transaction並立即執行一次read-only
> post-check。我批准預期建立197 People/member links、56 LINE identities、56 team_player及309 append-only audits。
> 任一gate失敗、timeout或狀態不明即依文件停止／判定，不批准重跑、ad-hoc SQL、audit deletion、trigger disable、
> destructive rollback／restore、Phase C、deployment、Secret／IAM／Scheduler／notification或其他production操作。

## Base commit

`9e552acaf277c1284ce48bbc2a78ba83137350fc`
