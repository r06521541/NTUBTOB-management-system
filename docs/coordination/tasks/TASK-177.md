# TASK-177：Anonymous Crash Reporting Foundation

## Task metadata

- task_type: `delivery`
- delivery_group: `task-177-anonymous-crash-foundation`
- requires_independent_pr: `true`
- acceptance_level: `L2`（privacy／local state；repository-only）
- base: `1a8f5e660fe731b3996577c22380050283473c31`
- branch: `codex/task-177-anonymous-crash-foundation`
- owner_approved: 2026-09-01

## Product outcome

建立 Flutter Android／iOS 共用、provider-neutral 的匿名 crash reporting 基礎。使用者未明確 opt in 時不收集；
opt in 後只允許本機保存固定 schema、嚴格去識別化的 bounded event，且 repository delivery 不包含任何外部
provider、endpoint、SDK、真實上傳或 store mutation。

## Required behavior

1. 預設關閉。只有 installation-local 明確 opt in 才能記錄；opt out 必須清除既有 crash queue。
2. Event schema 只允許 version、source、固定 failure category、UTC bucket、app flavor、platform class及由
   first-party frame canonicalization 產生的 opaque fingerprint；不得保存 raw error、message、stack、URL、route、
   request／Person／identity／installation ID、token、payload、notification content或device identifier。
3. Queue 使用既有 `DurableStore`，按 installation namespace 隔離，但 payload 不含 installation ID。固定限制 event
   count、單筆大小、總大小與 retention；corrupt／oversized／future payload fail closed並清除。
4. Capture／queue failure不得造成第二次 crash、不得改變原始 Flutter framework／platform error propagation。
5. Provider sink為抽象介面；本task不提供network implementation。沒有明確 sink時不得 drain、不得假稱 receipt。
6. Fake mode保持deterministic、fictional、network-free，且不建立durable crash collection。
7. Android Closed Testing／iOS TestFlight維持「未啟用、未收集」；public release仍需未來Owner-gated provider、
   privacy/store答案、synthetic receipt、真機、rollback及external disable evidence。

## Tests and acceptance

- config/default-off與unknown-value fail closed。
- schema固定、error／stack輸入不會出現在serialized event，first-party-only fingerprint穩定。
- opt-in capture、opt-out purge、retention、overflow、corrupt/future payload與write failure。
- serialized capture避免concurrent lost update；sink absent不drain，retry保留，accepted／terminal移除。
- Flutter framework／platform／zone hooks保留既有handler語意；fake composition不啟用collector。
- focused Flutter tests、full Flutter test/analyze/format、independent privacy/security review及hosted full gate。

## Current claim

- actor_id: `/root`
- role: `main-work`
- claim_id: `task-177-main-implementation-20260901`
- lease_version: 1
- report_to: Owner
- owned_paths: `clients/flutter_app/**`, `docs/releases/MOBILE_RELEASE_MATRIX.md`, this task／report／HANDOFF and
  directly related repository tests
- forbidden_paths: provider SDK／endpoint, cloud／Secret／store console, production runtime/data, release signing,
  deployment and unrelated services

## Stop conditions

- Useful diagnostics require retaining raw error text, raw stack, user/content identifiers or provider payload.
- A provider／endpoint／SDK、store form、real device、production runtime or external data becomes necessary.
- Queue cannot remain bounded or opt-out cannot transactionally stop future capture and purge retained events.
- Existing release contracts require claiming anonymous crash collection before external receipt evidence exists.
