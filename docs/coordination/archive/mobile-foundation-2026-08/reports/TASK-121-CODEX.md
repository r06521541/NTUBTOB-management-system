# TASK-121 Codex report — staging mobile principal aggregate diagnostic

## Result

- Added `--inspect-mobile-principal`, a candidate-gated read-only diagnostic
  that validates the approved database identity and exact revision 0005 before
  querying any principal state.
- The diagnostic reads only fictional Person `-112001` access level/status/
  version and mutually exclusive active-session aggregate counts. It returns
  `no_active_sessions`, `expected_only`, `mixed_principals`, `other_only`, or
  `binding_drift`; non-exhaustive or invalid counts fail closed.
- `expected_person_match` is true only for active Officer version 2. Revoked
  sessions are excluded. The output deliberately cannot identify the session
  used by a particular client token.
- Neither SQL nor output includes session IDs, installation identifiers,
  tokens, attempts, assertions, idempotency values, hashes, encrypted payloads,
  provider subjects, or another Person's ID/role.

## Verification

- Bundled Python offline operator suite: 45 passed, 18 PostgreSQL-dependent
  tests skipped when no database URL was supplied.
- Disposable local PostgreSQL 16 integration: 18 passed, including no-active,
  expected-only multiple sessions, mixed, other-only, binding drift, revoked
  exclusion, expected Person role/version/status and before/after session-row
  equality proving the diagnostic performed no write.
- `py_compile`, Black 24.4.2, isort 5.13.2 and `git diff --check` are recorded
  after the final formatting pass.

## Unverified and external state

- PostgreSQL 15 and hosted Python 3.10 remain final hosted CI evidence.
- No staging, production, cloud, Secret, LINE, notification or external database
  operation was performed. The local PostgreSQL cluster used only fictional
  repository fixtures and was stopped after testing.

## Handoff

- Branch: `codex/task-121-staging-principal-diagnostic`
- Base: `e9d1d42e8447f3a96b35b8e4ee9644ea211978b6`
- Status / next actor: `ready_for_review` / Main Work after commit and push.
