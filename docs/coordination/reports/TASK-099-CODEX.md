# TASK-099 Codex delivery report

## Outcome

TASK-099 closes the schema-neutral Portal management gaps with a deterministic
fictional localhost workflow, allowlisted-Admin basic/officer assignment,
request-time role navigation and management hub, Windows-safe dates, and
local-preview persisted-Admin read parity.

Planning commit: `0c047f6b7395bd885287e68780b7ccf6ded635b4`

Implementation commit: `a9bf9878f9ce1d2e896aac15f95eee01453f73e4`

## Delivered

- Added a deterministic fictional fixture operator with explicit confirmation,
  loopback/exact-database/revision gates, exact repository-or-demo state
  recognition, transactional seed/reset/cleanup, drift rejection, and rollback.
  It creates only reserved fictional IDs and never logs row values.
- Kept cloud-derived preview POSTs read-only. Only the explicit fictional flag
  plus the complete recognized fixture permits the audited Person access route;
  every other preview POST remains denied.
- Added transactional `basic <-> officer` access changes using the existing
  admin lock and audit table. The contract revalidates the actor and target,
  requires reason/request ID, rejects replay, self-change, admin targets,
  invalid transitions, Officer callers, and inactive promotion.
- Added `/manage`, made Person pages allowlisted-Admin-only, and centralized
  role-aware navigation. Basic uses `/future-games`; active Officer and
  allowlisted Admin use `/manage/games`; only Admin sees Person management.
- Cached the freshly resolved lifecycle principal only within one Flask request,
  avoiding a duplicate template-context database lookup without persisting a
  role in the signed session or weakening mismatch cleanup.
- Restored local-preview Admin repository read parity behind an explicit runtime
  constructor option. Production remains runtime-allowlist-only.
- Replaced POSIX-only date directives in Game and Attendance display. Attendance
  is available to active members and reports bounded database read failures as a
  safe partial-load state; unexpected programming exceptions still surface.
- Added the fictional demo runbook and explicit separation warning in the
  production-shaped preview runbook.

## Verification

- Bundled Python full Web Portal suite: `163 tests`, `OK`, `2 skipped`.
- Bundled Python affected portal-data offline modules: `41 tests`, `OK`,
  `31 skipped` because no database URL was set for that run.
- PostgreSQL 15: affected integration modules `10 + 29 tests`, all `OK`.
- PostgreSQL 16: affected integration modules `39 tests`, all `OK`.
  These prove repository-fixture seed, deterministic reset, cleanup, arbitrary
  drift denial, late-failure rollback, preview-Admin parity, production
  allowlist denial, and audited access readback/replay denial.
- Packaged shared library: local wheel built and imported through its installed
  `shared_module` path with a fake loopback DSN; no connection was opened.
- Affected modules `py_compile`: passed.
- Black 24.4.2 formatter API and isort 5.13.2 with `profile=black`: passed for
  every affected Python file. The Windows Black CLI stalled and was terminated
  per the environment guidance.
- `git diff --check`: passed.
- Local fictional browser QA used the actual repository/caller/database paths.
  Desktop and 390x844 both covered Basic, Officer, and Admin navigation and
  direct authorization: Basic `/manage` and Person are 403; Officer `/manage`
  works and Person is 403; Admin can open both. At 390px, all three dashboards
  had `scrollWidth=375` with `innerWidth=390`, and nav targets were Basic
  `/future-games` versus Officer/Admin `/manage/games`. Desktop Admin also
  exercised basic-to-officer POST, PRG, and readback; Attendance rendered the
  Windows-safe timestamp and fictional reply groups.

## Known environment-only failure

The broader pre-existing portal-data offline discovery ran `222 tests` with
`102 skipped` and three checksum errors for TASK-065/identity-drift controlled
SQL artifacts. Those files were not changed by TASK-099; this Windows checkout
materializes them with CRLF while the legacy verifiers hash raw bytes. The same
run under escalated filesystem access eliminated the two sandbox-only temporary
fixture write errors. No checksum artifact or verifier was changed in this task.

## Boundaries and cleanup

- Database revision remains `0004_phase_c_identity_lifecycle`; no migration,
  schema, controlled SQL, model field, export contract, production data, or
  cloud resource changed.
- Production Admin authority remains `WEB_PORTAL_ADMIN_MEMBER_IDS`. Persisted
  Person Admin is recognized only in exact localhost preview mode, and
  production Person Officer remains bounded to Game routes.
- No Supabase, Secret, production DB, deploy, IAM, Scheduler, crawler/weather,
  notification, LINE, Discord, or other external-service call was made.
- Browser QA used only loopback PostgreSQL containers and fictional rows. The
  app processes stopped, fictional fixtures were cleaned, all temporary
  containers were removed, the browser viewport was reset, and QA tabs closed.
- The original dirty worktree and excluded
  `tools/portal_preview_owner_bundle.py` were never modified. No PR was created.
