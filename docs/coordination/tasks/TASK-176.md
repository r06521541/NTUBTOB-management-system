# TASK-176：Persistent Admin Authority Core

## Task metadata

- task_type: `delivery`
- delivery_group: `task-176-persistent-admin-authority`
- requires_independent_pr: `true`
- acceptance_level: `L3`（authorization／schema；repository-only）
- base: `7dc96ed3fbb9ebb668a0f99749a9e987f0cd54e3`
- branch: `codex/task-176-admin-authority-core`
- owner_approved: 2026-09-01

## Product outcome

建立可稽核的持久化 Web Portal admin authority，使 production 未來可從
`WEB_PORTAL_ADMIN_MEMBER_IDS` runtime allowlist 受控切換到 active Person 的
`portal_access_level=admin`。本任務只交付 repository contract、migration、管理流程與測試；
不讀取真實 allowlist 值，不連 production database，不部署、不切換 runtime mode。

## Required behavior

1. Authority mode 嚴格為 `legacy_allowlist` 或 `persistent`；同一 request 只使用一種來源。
   缺失、未知或 drift 一律 fail closed，persistent 模式不得 union、fallback 或重新讀取 allowlist。
2. Persistent admin 必須同時是 active Person、`portal_access_level=admin`，且至少有一個 active linked
   login identity；Member 關係不是必要條件。
3. 使用單一 canonical `ADMIN_LOCK_KEY` 序列化所有會改變 admin reachability 的 mutation。
   若同時需要 Event lock，順序固定為 Admin → Event；鎖內重新讀取 actor、target、identity、status、role、version。
4. Admin grant／revoke 必須有 fresh reauthentication、CSRF、reason、request ID、expected version、exact replay、
   append-only audit與transaction rollback。禁止 self-lockout、禁止移除最後一位可登入 persistent admin。
5. Migration沿既有線性head新增最小 authority state／mode／epoch；重用 `people.portal_access_level`、status及
   `access_audit`，不得建立第二套Person role table。舊runtime在切換前維持安全相容。
6. 提供 repository-owned、預設read-only的去識別化 inventory／preflight contract，只輸出mode、分類與count；
   不輸出Member／Person／identity ID、名稱、provider subject、allowlist值或digest。
7. Production seed、mode flip、runtime部署、allowlist移除及rollback observation均是後續Owner-gated work package；
   本次merge不授權任何一項外部mutation。

## Tests and acceptance

- migration upgrade與pre-head相容性；unknown/future revision fail closed；不自動刪除authority/audit evidence。
- legacy與persistent principal resolution、unknown mode、no fallback、active-linked predicate。
- grant／revoke成功、replay mismatch、stale version、self／last-admin denial、audit/transaction rollback。
- competing status／identity／role mutation的PostgreSQL lock-order與last-admin concurrency。
- Web CSRF、fresh reauthentication、capability separation與非admin denial。
- inventory/preflight固定去識別化輸出與禁止敏感值的測試。
- writer focused tests、自評與immutable commit；一位獨立Auth/Security reviewer；最後一個hosted full gate。

## Sole writer claim

- actor_id: `/root/task170_play_evidence_writer`
- role: `codex-writer`
- claim_id: `task-176-admin-core-writer-20260901`
- lease_version: 1
- report_to: `/root`
- owned_paths: migration `0012`, relevant `shared_lib/shared_module/**`, `apps/web_portal/**`,
  repository-owned admin preflight under `tools/**`, focused tests, one TASK-176 report, this task and final HANDOFF status
- forbidden_paths: deployment/cloud/Secret/provider operators, production data artifacts, broker fixture/adapter,
  unrelated services and archive

### Lease 1 accepted compatibility expansion

Main accepted one narrow scope expansion after the writer proved that the existing Mobile API startup gate rejected a
linear 0012 head. `apps/mobile_api/revision_readiness.py` and its focused test are owned only to accept and classify exact
`0012_persistent_admin_authority` while retaining the prior historical revisions and rejecting malformed, unknown or
future values. No endpoint, Apple configuration, provider, auth, deployment or other Mobile runtime behavior is in scope.

Main also accepted the Phase C verifier and its directly corresponding tests only to classify exact
`0012_persistent_admin_authority` as the single current Alembic head. The checksummed 0001–0003 artifact and all
historical revision semantics remain unchanged; unknown, future and branched heads still fail closed.

Main accepted one test-only isolation path so the existing Event guest cleanup first removes exact retained 0012
authority evidence on the guarded localhost test database, then performs its unchanged exact-0011 cleanup. Unknown,
multi-head, nonlocal and future revisions still stop before DDL; no migration or runtime cleanup behavior changed.

Main accepted one hosted-targeted repository contract fixture correction so admin mutation actors are deterministic,
fictional active people with linked identities. The explicit unlinked-admin denial case and all product authorization
behavior remain unchanged.

### Lease 2 independent-review correction

Independent review required exact 0012 durable/runtime mode agreement in both directions, including the legacy path,
and canonical ADMIN-then-EVENT serialization before Apple provider revocation reads any identity or reachability row.
The correction preserves only exact 0011 deploy-new-runtime-first legacy compatibility when the 0012 authority table is
absent. Retained authority evidence, missing/malformed/multiple state and reverse mode mismatch remain fail closed.
Provider revocation remains terminal; disabling the last reachable persistent administrator keeps persistent mode,
records bounded recovery-required audit evidence and never falls back to the allowlist.

Writer must ACK `received/executing`, send heartbeat every 10–15 minutes, report blockers immediately, and proactively
deliver full SHA, dirty paths, tests, findings, limits and external mutations. Writer may commit and push the task branch,
but must not create/merge a PR or perform external runtime actions.

## Stop conditions

- Existing executable contracts require two simultaneous admin authority sources.
- Correct implementation requires a real allowlist value, real account identifier or production row.
- Last-admin safety cannot be proven transactionally with the canonical lock order.
- Migration cannot preserve safe compatibility with the current pre-0012 runtime.
- Any production, cloud, Secret, provider, deployment or real-data mutation becomes necessary.
