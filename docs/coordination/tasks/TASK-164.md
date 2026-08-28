# TASK-164 Event management production rollout

## Classification

- task_type: production rollout safety delivery
- risk: L3 production schema／runtime deployment
- delivery_group: `event-management-production-rollout`
- authority_branch: `codex/task-164-production-0004-to-0009-recovery`
- repository_authority: `39be8134739c2b0881e522af851c2973780d2027`
- Owner authorization: 2026-08-28 明確授權在原0008 premise安全停止後，重建production 0004→0009 recovery並於驗收後重新提出exact execution

## Active writer claim

- role: `codex-writer`
- claim_id: `task-164-production-0004-to-0009-recovery-writer-20260828`
- lease_version: 2
- actor_id: `/root/task160_web_portal_writer`
- state: `completed`
- report_to: `main-work`
- scope: repository-only exact 0004→0009 production migration recovery operator、private launcher、direct tests與task report
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
- stop_conditions: production identity無法fail-closed判定、需讀取／記錄Secret、非0004 revision、constraint/catalog drift、正式資料DML、notification／provider／IAM need、或unexpected dirty overlap

Lease 1 已完成原0008→0009 operator並於PR #211合併；2026-08-28首次production唯讀執行證明live revision並非0008，該source premise由Main撤回並以lease 2取代。未執行migration或deployment。

## Authorized outcome

1. 以受checksum與測試保護的operator接受repository-external private database input，且不得顯示、記錄或持久化連線資料。
2. Recovery operator僅允許exact `0004_phase_c_identity_lifecycle` → `0009_event_management_writes`，先鎖定並驗證單一Alembic revision、0004 Event／identity邊界及0005–0009將建立／修改的object absence，再以單一transaction執行既有migration chain並做exact postcheck。
3. `dry-run`／preflight不得mutation；execute需exact merged commit、clean main、短效acknowledgement與Owner在隱藏prompt輸入private database URL。任何未知、already-forward、divergent或ambiguous state均停止，不自動retry。
4. Migration不得建立／刪除Event、Activity、invitee、audit資料，不得發通知；rollback保留擴充constraint與audit evidence，runtime失敗以Web traffic切回exact prior revision處理。
5. Operator recovery經independent Data／Security review與hosted PostgreSQL 15／16通過後，Main才可重新請求production execution。
6. Database postcheck通過後，以existing `tools/deploy_web_portal.py`部署exact merged main；保留`web-portal-00051-p4z`為rollback，flags維持Phase C=true、freeze=false、identity maintenance=true、identity-link disabled，Secret references／runtime identity／public boundary不變。
7. 部署後只做既有無副作用HTTP與control-plane checks；不建立Event、不改正式資料、不發通知。產品寫入smoke留給Owner後續人工操作。

## Verification budget

- Writer：operator unit、no-disclosure／wrong-target／revision drift／one-shot／rollback semantics，及isolated PostgreSQL 15／16 exact transaction tests。
- Independent reviewer：只檢查production identity、Secret non-disclosure、catalog gate、transaction與no-DML boundary。
- Main：diff／scope、focused tests、一次hosted gate。
- Production：先前0008 source mismatch未連成migration；recovery合併後重新核准一次read-only preflight、一次0004→0009 migration attempt、一次Web deployment；失敗依stop condition停止或切回exact rollback revision，不盲目retry。

## Current evidence

- Recovery branch由`main`／`origin/main` exact `39be8134739c2b0881e522af851c2973780d2027`建立；分支建立前worktree clean。
- PR #209 final hosted run `33077406624` 全綠；0009 repository migration已驗收合併。
- Web production read-only preflight：exact project／service、latest Ready=`web-portal-00051-p4z`、100% traffic、public invoker、runtime identity與4個base Secret references存在；Phase C=true、freeze=false、identity maintenance=true、identity-link keys absent。
- 原operator的Cloud/repository preflight passed；首次production DB唯讀precheck接受private target但因revision非0008停止。未讀取Secret payload、未執行database／runtime mutation。

## Writer delivery checkpoint

- Repository operator recovery須以canonical-LF checksum鎖定launcher、operator、既有0005–0009 migrations、Alembic env與config；不修改既有migration或deployment wrapper。
- Launcher只允許clean且同步origin/main的exact merged `main`進行dry-run或execute，從隱藏prompt接收private URL，並以read-only Cloud Run Ready revision metadata將DSN host／port／database／user逐欄比對；不讀Secret payload、不輸出account、URL、env list或Secret reference。
- Execute僅接受clean exact merged `main`／`origin/main`與Owner批准full SHA；資料庫端只接受exact 0004及所有0005–0009 touched-object前置邊界，單一transaction升到0009並證明application-table DML為零。Already-forward、divergent、drift或不確定狀態均停止且不retry。
- Local Python 3.10 unit／static evidence已通過；本機沒有isolated PostgreSQL URL，因此PostgreSQL integration保留為hosted PostgreSQL 15／16 gate，尚未宣稱通過。
- Independent Data／Security reviewer經五輪adversarial review後`ACCEPT`；Main focused 28 outcomes（22 passed、6 local PostgreSQL skipped）、adjacent 17 outcomes（11 passed、6 skipped）、artifact與diff checks通過。Hosted PostgreSQL 15／16仍是merge前required gate。
