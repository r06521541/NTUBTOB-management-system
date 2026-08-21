# TASK-121 — Staging mobile principal aggregate diagnostic

- Task type: delivery
- Delivery group: staging-mobile-principal-diagnostic
- Base: `e9d1d42e8447f3a96b35b8e4ee9644ea211978b6`
- Implementation branch: `codex/task-121-staging-principal-diagnostic`

## Goal

Add one aggregate-only, read-only staging operator action that helps distinguish
whether active mobile sessions belong to the TASK-119 fictional Officer Person.
The diagnostic is evidence for Main Work; it does not identify the session used
by a particular client token.

## Scope

- `tools/mobile_staging_data.py`
- `tools/tests/test_mobile_staging_operator.py`
- `docs/operations/mobile/MOBILE_STAGING.md`
- this task and the single TASK-121 Codex report

## Invariants

- Require candidate approval, the exact approved database identity, revision
  `0005_mobile_auth_api_foundation`, and an explicit read-only transaction.
- Query only Person `-112001` access level/status/version and mutually exclusive
  active-session counts: total, expected tuple, expected-Person identity binding
  mismatch, and other principal. The three categories must sum to total.
- Output only safe aggregate classification and Person role state. Never select,
  compare, log, or output a session ID, installation identifier, token, refresh
  attempt, provider assertion, idempotency value, hash, encrypted payload, or
  provider subject. Do not expose another Person's ID or role.
- No schema, migration, model, runtime API, Flutter, staging, Secret, cloud,
  production, notification, or external mutation.

## Verification

Cover empty, multiple expected sessions, mixed/other/binding-drift states,
revoked-session exclusion, Person role/status/version mismatch, SQL error
redaction, CLI output-field safety, PostgreSQL aggregate correctness and zero
writes. Run the affected offline suite, local PostgreSQL 16 when available,
py_compile, Black/isort and Git diff/status. PostgreSQL 15 and hosted Python 3.10
may remain final hosted evidence.
