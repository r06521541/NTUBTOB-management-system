# TASK-164 Event management production rollout

## Classification

- task_type: production rollout safety delivery
- risk: L3 production schema／runtime deployment
- delivery_group: `event-management-production-rollout`
- authority_branch: `codex/task-164-event-production-rollout`
- repository_authority: `aa614ab57423f589d318bc96c627d5f5a1b61bb5`
- Owner authorization: 2026-08-27 明確同意 TASK-163 production 0008→0009 migration 與 exact merged Web Portal rollout

## Active writer claim

- role: `codex-writer`
- claim_id: `task-164-event-rollout-operator-writer-20260827`
- lease_version: 1
- actor_id: `/root/task160_web_portal_writer`
- state: `active`
- report_to: `main-work`
- scope: repository-only exact 0008→0009 production migration operator、private launcher、direct tests與task report
- owned paths:
  - `tools/portal_data_event_management_rollout.py`
  - `tools/portal_data_event_management_rollout.py.sha256`
  - `tools/launch_production_event_management_rollout.py`
  - `tools/launch_production_event_management_rollout.py.sha256`
  - `tools/TASK-164-event-rollout-materials.sha256`
  - `tools/tests/test_production_event_management_rollout.py`
  - `tests/portal_data/test_event_management_rollout.py`
  - `docs/coordination/tasks/TASK-164.md`
  - `docs/coordination/reports/TASK-164-CODEX.md`
- write: exact task branch and owned paths only；writer可commit/push handoff，Main負責acceptance、PR、merge與production execution
- stop_conditions: production identity無法fail-closed判定、需讀取／記錄Secret、非0008 revision、constraint/catalog drift、正式資料DML、notification／provider／IAM need、或unexpected dirty overlap

## Authorized outcome

1. 先交付一個受checksum與測試保護的operator，只接受repository-external private database input，且不得顯示、記錄或持久化連線資料。
2. Operator僅允許exact `0008_mobile_notification_delivery` → `0009_event_management_writes`，先鎖定並驗證單一Alembic revision、舊`event_audit` action constraint、append-only／RLS／policy邊界，再以單一transaction執行既有0009 migration並做exact postcheck。
3. `dry-run`／preflight不得mutation；execute需exact merged commit、clean main、短效acknowledgement與Owner在隱藏prompt輸入private database URL。任何未知、already-forward、divergent或ambiguous state均停止，不自動retry。
4. Migration不得建立／刪除Event、Activity、invitee、audit資料，不得發通知；rollback保留擴充constraint與audit evidence，runtime失敗以Web traffic切回exact prior revision處理。
5. Operator PR經independent Data／Security review與hosted PostgreSQL 15／16通過後，Main才可執行production migration。
6. Database postcheck通過後，以existing `tools/deploy_web_portal.py`部署exact merged main；保留`web-portal-00051-p4z`為rollback，flags維持Phase C=true、freeze=false、identity maintenance=true、identity-link disabled，Secret references／runtime identity／public boundary不變。
7. 部署後只做既有無副作用HTTP與control-plane checks；不建立Event、不改正式資料、不發通知。產品寫入smoke留給Owner後續人工操作。

## Verification budget

- Writer：operator unit、no-disclosure／wrong-target／revision drift／one-shot／rollback semantics，及isolated PostgreSQL 15／16 exact transaction tests。
- Independent reviewer：只檢查production identity、Secret non-disclosure、catalog gate、transaction與no-DML boundary。
- Main：diff／scope、focused tests、一次hosted gate。
- Production：一次read-only preflight、一次migration attempt、一次Web deployment；失敗依stop condition停止或切回exact rollback revision，不盲目retry。

## Current evidence

- `main`／`origin/main`／HEAD exact `aa614ab57423f589d318bc96c627d5f5a1b61bb5`，worktree clean。
- PR #209 final hosted run `33077406624` 全綠；0009 repository migration已驗收合併。
- Web production read-only preflight：exact project／service、latest Ready=`web-portal-00051-p4z`、100% traffic、public invoker、runtime identity與4個base Secret references存在；Phase C=true、freeze=false、identity maintenance=true、identity-link keys absent。
- Repository dry-run passed；未讀取Secret payload、未查production DB、未執行cloud／database mutation。

## Writer delivery checkpoint

- Repository operator以canonical-LF checksum鎖定launcher、operator、既有0009 migration、Alembic env與config；不修改migration或deployment wrapper。
- Launcher只允許clean且同步origin/main的exact merged `main`進行dry-run或execute，從隱藏prompt接收private URL，並以read-only Cloud Run Ready revision metadata將DSN host／port／database／user逐欄比對；不讀Secret payload、不輸出account、URL、env list或Secret reference。
- Execute僅接受clean exact merged `main`／`origin/main`與Owner批准full SHA；資料庫端只接受exact 0008舊constraint／append-only／RLS／zero-policy狀態，單一transaction升到0009並證明application-table DML為零。Already-forward、divergent、drift或不確定狀態均停止且不retry。
- Local Python 3.10 unit／static evidence已通過；本機沒有isolated PostgreSQL URL，因此PostgreSQL integration保留為hosted PostgreSQL 15／16 gate，尚未宣稱通過。
