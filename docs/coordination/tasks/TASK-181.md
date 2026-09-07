# TASK-181：工程減摩擦

- type: `delivery`; delivery_group: `task-181-engineering-friction`
- requires_independent_pr: true（同一實質工具變更與文件單一PR）; write: allowed
- acceptance_level: `L2`（local quality path selection；不改 CI／runtime）
- Owner request: 2026-09-07「做這包」；既有 Git standing authorization 維持。
- base: `9a5158ab285dad6f60e51dff520106104aaf0cb0`
- branch: `codex/task-181-engineering-friction`
- claim_id: `task-181-engineering-friction-20260907`; lease_version: 1
- actor_id: `/root`; role: `main-work`; report_to: `/root`
- 前 TASK-180 writer claim 已完成 repository delivery，由 base Git commit 證明；不延續其 writer lease。

## Scope / owned paths

- `README.md`, `apps/mobile_api/README.md`, `AGENTS.md`：校正本機入口與過期敘述，不改安全授權。
- `docs/development/AGENT_ENVIRONMENT.md`, `docs/development/ENGINEERING_FRICTION_PROPOSAL.md`：
  操作說明與尚未生效的流程／CI 建議。
- `tools/repository_quality.py`, `tools/tests/test_repository_quality.py`：沿用既有 runner，新增 working-tree selection。
- `docs/README.md`, `docs/coordination/PROJECT_STATE.md`, `docs/coordination/HANDOFF.yaml`：
  區分 repository 整合證據與未重新查證的 runtime 紀錄。
- 本 task、`docs/coordination/reports/TASK-181.md`：單一工作包與 evidence。

## Invariants / acceptance

1. 不新增 formatter/wrapper、不改 CI classifier/workflows、Secret／provider／cloud／DB／產品行為。
2. Working-tree check 包含 staged、unstaged、untracked non-ignored Python，排除已刪除檔；
   檢查相對HEAD的最終磁碟內容，不聲稱驗證 index snapshot（抵銷回HEAD者不入選）。Unsafe paths、Git failure 保持 fail closed。
3. `--working-tree` 僅供 check；format 仍須 explicit paths 或既有明確 selection，避免誤改他人 dirty work。
4. 既有版本、timeout、no-shell、no-source-output 與 SHA-based CI selection 不變。
5. 文件提案非 authority；review／Owner gate／識別碼分類／CI evidence 重用的改制不在本次生效。
6. Focused quality tests（含 temporary Git repo 的 staged/unstaged/untracked/deleted/rename）、
   formatter check、classifier/workflow 回歸、独立 targeted review；單一 final PR，hosted gate 依現行 classifier。

## Stop conditions

需要讀機密、外部 runtime mutation、放寬 CI／授權或不明 dirty overlap 時停止該部分；繼續不受阻部分。
獨立 reviewer 使用 read-only assignment packet，立即 ACK、blocker 即報、完成主動送回 `/root`；Main bounded wait。

## Independent reviewer claim

- actor_id: `/root/task181_review`; role: `advisor`; write: read-only
- claim_id: `task-181-review-20260907`; lease_version: 1; report_to: `/root`
- scope: 本task owned diff、quality selection安全／測試，以及文件是否意外放寬authority。
- owned_paths: 無（唯讀）；base同上，審查當前dirty diff，完成前重查變動。
- stop_conditions: dirty diff被其他writer更改、需外部操作、需寫檔。
- verdict: ACCEPT；48 tests（47 passed，1 local Bash skip）、diff check通過，Main已收到completion。
