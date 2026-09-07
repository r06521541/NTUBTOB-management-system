# TASK-182：本機工具穩定化

- type: delivery; delivery_group: task-182-local-tool-stability; requires_independent_pr: true
- acceptance_level: L2（quality subprocess／launcher helper；無外部操作）
- Owner request: 2026-09-07「請做」本機工具穩定化三項；流程與CI gate不放寬。
- base: `c780f2499a0b08c634ee531258db37c711eeeb92`
- branch: `codex/task-182-local-tool-stability`
- actor_id: `/root`; role: main-work; claim_id: task-182-local-tool-stability-20260907
- lease_version: 1; write: allowed; report_to: `/root`
- TASK-181已由base合併，其writer/reviewer工作已終結，不沿用其claim。

## Owned scope

- `tools/repository_quality.py`, `tools/tests/test_repository_quality.py`：隔離Black cache、固定安全修復提示與回歸。
- `tools/Invoke-MobileStaging.ps1`, `tools/tests/test_mobile_staging_launcher.py`：
  僅本機process helper的空參數／UTF-8修正與虛構process測試；不執行launcher action。
- `docs/development/AGENT_ENVIRONMENT.md`：根因、使用方式與限制。
- `docs/coordination/HANDOFF.yaml`, `docs/coordination/PROJECT_STATE.md`、本task與唯一report。

## Invariants / tests

- pinned formatter CLI、版本驗證、timeout/no-shell、既有selection與CI保持不變；不改全域cache或ACL。
- cache僅本次子程序使用且自動清理；不記source／exception／secret。錯誤提示不推定任何runtime mutation結果。
- PowerShell參數值不丟失；UTF-8 round-trip；exit code而非stderr有無判成功；空／單／多筆結果在StrictMode下安全。
- 使用明顯虛構child process；不接觸cloud、DB、private config、ADB、signing、approval或可部署產物。
- 先重現再修改；quality suite＋launcher focused/full local、現有CI contract、獨立targeted review與單一ready PR hosted。
- launcher helper改動不沿用任何舊exact approval；本task不授權操作新版launcher的外部actions。

## Stop conditions

需要機密、真實runtime操作、放寬批准／重試規則、無法處理的他人dirty overlap時停止該部分。

## Independent reviewer

- actor_id: `/root/task181_review`; role: advisor; write: read-only; owned_paths: none
- claim_id: task-182-review-20260907; lease_version: 2; report_to: `/root`
- 先前TASK-181 reviewer claim已完成；本claim僅審本task dirty diff與直接測試，不兼任writer。
- ACK立即、blocker即報、完成主動送verdict/HEAD/dirty/tests/limits/external mutations到Main；Main bounded wait。
- lease1已接受核心diff；lease2只增量核對PowerShell test-harness module environment與新增bootstrap回歸。
- lease2 verdict: ACCEPT；Main已接收，完整83項本機PASS；hosted gate待single ready PR。
