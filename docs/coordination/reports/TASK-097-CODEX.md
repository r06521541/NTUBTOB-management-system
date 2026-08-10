# TASK-097 Codex delivery report

## Outcome

TASK-097 now provides a fixed, Owner-operated read-only export contract and a
private localhost preview pipeline:

`fixed JSONL export -> manifest/checksum validation -> deterministic pseudonymization -> transactional ntubtob_portal_local import -> loopback-only read-only Portal`

Planning commit: `0114ca8c9ca64ea5cc5d34f1a9fe84c78f92bc32`

Latest implementation commit: `f4c0aa7c5cc552f02df288132e774024dabc4220`

Prior fixture-replacement commit: `71e6e0dd4ef70fe7f99d566570d8c9307a3ea281`

Initial implementation commit: `3ccd2f49e900b1b2ca07fe478a160cdad0566a26`

## Delivered

- Six fixed `BEGIN TRANSACTION READ ONLY` SQL contracts cover only the required
  Game, Member, Attendance, Person, Identity, and Qualification fields. They omit
  raw provider subjects, provider user IDs, administrative notes, audit payloads,
  qualification reasons, credentials, tokens, and secrets.
- `tools.portal_data_local_preview` seals raw private JSONL files with a strict
  manifest and per-file SHA-256, rejects repository-local artifact paths, validates
  the exact table/field/type/revision/row-limit/FK contract, and emits no row values
  in errors.
- Deterministic HMAC pseudonymization remaps all IDs, names, teams, fields, major,
  identity subjects, enrollment years, and timestamps while preserving foreign
  keys, cardinality, linked Person/Member names, jersey numbers, positions,
  qualification validity, attendance replies, and relative timing.
- The importer reuses `require_local_database_url`, accepts only the named isolated
  local database at revision `0004_phase_c_identity_lifecycle`, and accepts only
  an empty target or the exact repository-owned `setup_portal_data_legacy` plus
  `0004` fixture. It fingerprints and replaces that fixture together with the
  bundle insert in one transaction; arbitrary nonempty/drifted data fails closed.
  A late constraint failure restores the fixture and a corrected retry succeeds.
- `/local-preview/login` uses only safe pseudonymous projections. Startup requires
  exact development/preview flags, loopback bind, and matching local URL/DSN.
  Non-loopback Hosts and LINE login/callback fail closed; all Portal POST mutations
  except preview session login/logout return 403 before repository or external
  side effects. Formal production routes continue using existing repositories,
  callers, capability policy, session, CSRF, and templates.
- The PowerShell runbook pins the bundled Python, separates Owner-only export from
  Codex operations, uses the existing local Compose database, and defines exact
  private-artifact and named-volume cleanup boundaries.
- Repository tools import the shared helper through the checkout namespace
  `shared_lib.shared_module`; Web Portal tests expose the source package root as
  `PYTHONPATH`, so runtime code continues to use only its packaged
  `shared_module` namespace. The URL gate remains a single implementation and no
  production fallback package was added.

## Verification

- Bundled Python `py_compile` for all affected Python modules: passed.
- Web Portal offline suite: `142 tests`, `OK`, `2 skipped`.
- Portal-data offline suite: `216 tests`, `OK`, `98 skipped` because no shared
  database URL was set for that offline run.
- Hosted-CI import failure reproduction: Web preview `4 tests`, `OK`; private
  bundle/security `5 tests`, `OK`; the preview app subprocess import also passed
  with only the source package root supplied as its packaged namespace.
- PostgreSQL 15.8 isolated importer integration: `3 tests`, `OK`; each starts from
  the real repository setup/migration fixture and covers success/readback,
  arbitrary nonempty drift denial, late constraint rollback, fixture restoration,
  and retry without test-only clearing.
- PostgreSQL 16.4 isolated importer integration: `3 tests`, `OK`; same contract.
- Black 24.4.2 and isort 5.13.2 (`profile=black`) formatter API, per affected
  Python file: passed. The bundled Windows Black CLI stalled without output as
  documented in `AGENT_ENVIRONMENT.md`, so it was terminated and replaced by the
  same-version formatter API/check.
- `git diff --check`: passed.
- Dedicated containers `task097-fix-pg15` and `task097-fix-pg16` were removed
  after verification.

## Boundaries and review notes

- No Supabase/source database connection, cloud export, credential/Secret read,
  production row, production mutation/schema change, deployment, IAM/Scheduler
  operation, external HTTP call, or LINE/Discord notification occurred.
- No raw/derived bundle or pseudonymization seed was created in or added to Git.
  Tests used only fictional rows in OS temporary directories.
- The fixed export SQL was statically and contract-tested but was not executed
  against any source environment. Actual export remains blocked until the Owner
  separately approves the exact commit, SQL, operator, target, and cleanup plan.
- Browser/LINE in-app visual smoke and any hosted deployment are not claimed.
- PostgreSQL 15/16 were not rerun for the import-path-only correction; the prior
  local 3/3-per-version transaction evidence remains unchanged, and PR #107 CI
  must provide final hosted Python 3.10 collection/integration evidence.
