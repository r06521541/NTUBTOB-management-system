# TASK-099 Codex delivery report

## Outcome

TASK-099 closes the schema-neutral Portal management gaps with a deterministic
fictional localhost workflow, allowlisted-Admin basic/officer assignment,
request-time role navigation and management hub, Windows-safe dates, and
local-preview persisted-Admin read parity.

Planning commit: `0c047f6b7395bd885287e68780b7ccf6ded635b4`

Initial implementation commit: `a9bf9878f9ce1d2e896aac15f95eee01453f73e4`

Changes-requested implementation commit:
`64ea3075cf60ec68676ec2cc1708074546430183`

Final cumulative-diff correction commit:
`f790589efa855060cc05e1ceed3eb5fb17edacb1`

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
- The access route now uses the shared bounded request-ID parser. Fictional
  access rehearsals additionally require the exact target/transition request
  ID and canonical reason, so repository state and audit rows have one exact
  fingerprint; malformed, oversized, and non-ASCII IDs fail before repository
  access.
- Seed and reset now require an explicitly validated, timezone-aware anchor and
  derive every Game/invitation/cancellation timestamp from it. Reset and
  cleanup reject unknown or duplicate `person-access-*` audit drift instead of
  treating a merely in-range row as repository-owned state.
- Added a focused <=420px density layer for narrower shell/card spacing and
  48px bottom-navigation targets. The final correction restores `games.py`
  from base `44925dad` and reapplies only the Windows-safe month/day rendering;
  cumulative base-to-HEAD diff is `2 additions, 4 deletions` in that method.

## Verification

- Bundled Python full Web Portal suite: `164 tests`, `OK`, `2 skipped`.
- Bundled Python affected portal-data offline modules: `41 tests`, `OK`,
  `31 skipped` because no database URL was set for that run.
- PostgreSQL 15: affected integration modules `10 + 29 tests`, all `OK`.
- PostgreSQL 16: affected integration modules `39 tests`, all `OK`.
  These prove repository-fixture seed, deterministic reset, cleanup, arbitrary
  drift denial, late-failure rollback, preview-Admin parity, production
  allowlist denial, and audited access readback/replay denial.
- Changes-requested PG15 and PG16 runs each executed the focused fictional
  bundle module from repository setup/migration state: `14 tests`, all `OK`.
  They cover anchor validation and complete timestamp equality after reset,
  exact access-audit acceptance, unknown-audit drift rejection, cleanup, and
  late-failure rollback/retry.
- Packaged shared library: local wheel built and imported through its installed
  `shared_module` path with a fake loopback DSN; no connection was opened.
- Affected modules `py_compile`: passed.
- Black and isort with `profile=black`: passed for every affected Python file.
- `git diff --check`: passed.
- Final `games.py` correction: direct `get_formatted_date()` assertion returned
  `8/10（一）`; targeted `py_compile` passed; cumulative
  `git diff 44925dad --check` passed. PostgreSQL and browser QA were not rerun,
  as Work explicitly waived them for this formatting-only correction.
- Local fictional browser QA used the actual repository/caller/database paths.
  Desktop and 390x844 both covered Basic, Officer, and Admin navigation and
  direct authorization: Basic `/manage` and Person are 403; Officer `/manage`
  works and Person is 403; Admin can open both. At 390px, all three dashboards
  had `scrollWidth=375` with `innerWidth=390`, and nav targets were Basic
  `/future-games` versus Officer/Admin `/manage/games`. Desktop Admin also
  exercised basic-to-officer POST, PRG, and readback; Attendance rendered the
  Windows-safe timestamp and fictional reply groups.
- Changes-requested 390x844 QA used the packaged shared library and PG16 fixture
  to recheck Admin dashboard, Person detail, exact access POST -> PRG -> basic
  readback, and Attendance. The pages had `innerWidth=390`,
  `scrollWidth=375`, a 355px shell, and 46px Person action controls; screenshot
  inspection confirmed the denser cards and fixed bottom navigation remained
  readable without horizontal overflow.

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
