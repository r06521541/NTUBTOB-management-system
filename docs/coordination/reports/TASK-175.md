# TASK-175 implementation report

## Outcome

- Added the linear additive `0011_event_notification_guest_lifecycle` migration.
  It retains notification and guest audit evidence on production downgrade while
  keeping the 0010 runtime compatible during rollout.
- Event publish, edit, and cancellation remain separate from notification. An
  authorized manager must preview and type-confirm the current immutable included
  invitee snapshot; the transaction creates recipient history, one succeeded
  in-app delivery, and append-only publish audit with durable idempotency. It
  creates no push or external-delivery work and accepts no client recipient IDs.
- Guest-player management now grants, extends, revokes, and derives scheduled,
  active, expired, or revoked state for an existing active Person. Mutations lock
  the Event snapshot boundary, require an expected version and reason, reject
  Member or active team-player overlap, and append a full before/after audit.
- The Web Portal exposes a narrow guest-manager surface for active persisted
  Officers and active allowlisted Member admins. The legacy broad qualification
  and identity-approval surfaces no longer grant guest-player state, and the
  narrow Officer authority does not open any broad identity/member administration.
- Production Person status writes explicitly acquire the canonical Admin lock and
  then the Event snapshot advisory lock before `_require_admin` reads or locks the
  actor row. The re-entrant Admin lock inside `_require_admin` remains intact, and
  the target row is read only after both advisory locks. This removes the actor-row
  versus Event-lock cycle while preserving active-recipient exclusion and rollback
  on audit failure.
- Web and Mobile Event reads expose only the caller's immutable participation
  category. Mobile notifications accept Event destinations; Flutter opens the
  authorized online Event detail and safely remains in notifications offline.
- Canonical repository migration readiness now recognizes 0011. Core Mobile API
  readiness remains compatible with 0008 through 0011, Apple lifecycle remains
  available at 0010 or 0011, and all new Event/guest writes require exact 0011.

## Verification

- `py -3.10 -m unittest discover -s apps/mobile_api/tests -v`: 77 passed.
- `py -3.10 -m unittest shared_lib.tests.test_event_read shared_lib.tests.test_mobile_api_service shared_lib.tests.test_notification_api_service -v`:
  36 passed.
- `$env:PYTHONPATH='.'; py -3.10 -m unittest discover -s apps/web_portal/tests -v`:
  243 passed after the targeted authorization corrections.
- `py -3.10 -m unittest tests.portal_data.test_event_guest_lifecycle tests.portal_data.test_phase_c_lifecycle -v`:
  49 cases: 11 passed and 38 expected isolated-PostgreSQL skips locally. The static
  regression observes `Admin -> Event -> re-entrant Admin -> actor -> target`
  instead of mocking `_require_admin`.
- `py -3.10 -m unittest discover -s tests/portal_data -v`: 312 cases: 154 passed
  and 158 expected skips without the isolated PostgreSQL URL.
- Added an isolated-PostgreSQL concurrency regression that runs a real Event
  notification preview holding the Event lock while `change_person_status`
  requests it. Both transactions must complete without deadlock; the preview
  serialized before the status mutation sees two recipients and the following
  preview excludes the disabled recipient.
- Flutter focused tests: 175 passed.
- Flutter analyze on the five affected files: no issues; Dart format check changed
  zero files.
- Python compileall over the migration, shared library, Mobile API, Web Portal,
  portal-data tests, and migration readiness tools: passed.
- Pinned Black formatter API comparison and isort checks on affected Python files:
  passed. Broad Black CLI was terminated after its known Windows high-CPU stall;
  no formatter process was left running.

## Hosted correction

- PR #229 run `33461913443` exposed three exact Python quality files and four
  PostgreSQL-only fixture/metadata compatibility problems. The files are now
  formatted individually with pinned Black 24.4.2 and isort 5.13.2; no broad
  repository formatter was used.
- Guest audit metadata now uses PostgreSQL JSONB exactly as 0011 creates it.
  `PersonQualificationRecord` disables eager non-primary server-default fetching,
  so 0004-0010 repository inserts do not add a `RETURNING version` reference before
  0011 exists. The existing additive 0011 version column and positive-version
  constraint are covered by an explicit regression.
- Event/guest PostgreSQL fixtures allocate isolated member IDs instead of colliding
  with legacy fixture IDs. Test classes restore the retained 0011 evidence boundary
  to 0010 after their head-only coverage, preventing revision leakage into adjacent
  suites.
- Phase C guest fixtures now approve a plain non-Member Person and then grant or
  revoke `guest_player` only through the formal versioned guest lifecycle. The
  blocked generic qualification path remains blocked.
- Local correction evidence: Web Portal full suite 243 passed; portal-data full
  suite 313 passed with 158 expected isolated-PostgreSQL skips; nine focused Event
  static regressions passed; Python compile passed; isort check and per-file Black
  API comparisons passed; Alembic reports the single
  `0011_event_notification_guest_lifecycle` head.

### Hosted correction lease 2

- The raw completed PostgreSQL 16 job `99719247947` contained exactly two errors
  and fifteen failures. The errors were one SQLAlchemy result-consumption error and
  one stale Event-manager fixture; the failures were twelve material-drift subtests
  and three exact 0010 revision checks. PostgreSQL 15 reported the same set.
- `scoped_events` now materializes the two-column SQLAlchemy result with `.all()`
  before converting it to a dictionary. A red-first focused regression reproduces
  the hosted `ChunkedIteratorResult` mapping behavior without PostgreSQL.
- The shared attendance contract now uses an active Officer for Event mutations
  and retains its separate Admin for Person-status mutation. Product authorization
  is unchanged and no persisted-Admin shortcut was introduced.
- The older Event rollout suite now upgrades and restores the exact
  `0010_apple_provider_lifecycle` revision it validates, rather than following the
  moving Alembic head into 0011. TASK-175 integration suites continue using the
  reviewed isolated-test cleanup helper; rollout drift detection and legacy exact
  revision assertions are unchanged.
- Local lease-2 evidence: the focused result and attendance regressions both
  passed; portal-data full suite 314 passed with 158 expected PostgreSQL skips;
  Web Portal full suite 243 passed.

### Hosted correction lease 3

- The Event rollout drift suite now uses a canonical test-only reset in class
  cleanup. It rebuilds the legacy fixture and upgrades to exact 0010, so the
  final material-drift mutation cannot leak into the next hosted suite merely
  because the Alembic revision label already reads 0010.
- The reset reuses the repository's isolated database identity and revision
  boundary. It rejects non-PostgreSQL, nonlocal, wrong-name, missing, branched,
  unknown, and 0011-or-later revisions before destructive DDL.
- Static regressions prove the fail-closed boundary and DDL ordering. An isolated
  PostgreSQL regression disables the final trigger-drift object, observes the
  expected failure, resets, then verifies exact revision 0010 and the complete
  canonical future-schema fingerprint. An ordered follower class independently
  verifies the next suite receives that canonical 0010 state.
- Local lease-3 evidence: 11 focused static regressions passed; portal-data full
  suite ran 318 tests successfully with 160 expected isolated-PostgreSQL skips;
  py_compile, pinned Black 24.4.2 per-file API comparison, isort 5.13.2, and diff
  checks passed. Hosted PostgreSQL 15/16 remains required for the real reset.

### Hosted correction lease 4

- Per-test Event rollout setup no longer performs a URL-only direct schema drop.
  It delegates to the same test-only guarded reset as class cleanup, with exact
  allowlisted targets: 0004 for each test fixture and 0010 after the class.
- The shared reset validates its target plus local isolated PostgreSQL identity
  and one known pre-0011 source revision before DDL. Missing, empty, unknown,
  0011-or-later, or branched revision state stops without beginning a transaction.
- Static regressions prove setup delegates to the guard and performs no direct
  transaction, while the existing PostgreSQL drift/reset/follower regressions
  retain clean 0004-per-test and canonical 0010-next-suite evidence.
- Local lease-4 evidence: 12 focused static regressions passed; the rollout module
  ran 11 tests successfully with 8 expected PostgreSQL skips; portal-data full ran
  319 tests successfully with 160 expected PostgreSQL skips. Hosted PostgreSQL
  15/16 remains required for the real guarded setup and cleanup sequence.

### Hosted correction lease 5

- PostgreSQL 16 job `99724128325` reduced the remaining failure set to three
  older integration fixtures. Each upgraded the moving Alembic `head` to 0011
  and then correctly asserted the historical schema revision it owns was 0010.
- Mobile API foundation, Mobile notification, and staging broker journal setup
  now upgrade explicitly to `0010_apple_provider_lifecycle`. Their exact revision,
  RLS, model, constraint, index, and downgrade assertions are unchanged.
- A static migration contract proves all three historical suites pin 0010 and
  the TASK-175 Event guest lifecycle suite remains the owner of current
  `head`/0011 coverage. Adjacent head callers either validate current head or
  immediately exercise an explicit downgrade; no fourth matching defect was
  found.
- Local lease-5 evidence: the red-first contract failed for all three moving-head
  fixtures, then passed after pinning; all 10 migration-readiness static tests
  passed; portal-data full ran 320 tests successfully with 160 expected
  PostgreSQL skips. Hosted PostgreSQL 15/16 remains required for the three
  integration assertions.

### Hosted correction lease 6

- PostgreSQL 15 job `99725514547` showed the Mobile notification suite was not an
  historical 0010 suite: it exercises the current notification ORM, including
  `mobile_notifications.destination_event_id`, which belongs to additive 0011.
- Mobile notification setup again upgrades current `head` and its exact revision
  assertion now requires `0011_event_notification_guest_lifecycle`. All RLS,
  database/model column, constraint, delivery, and notification service assertions
  remain unchanged.
- The static ownership contract now classifies exactly Mobile API foundation and
  staging broker as historical 0010 suites, while Mobile notification and Event
  guest lifecycle own current head/0011 integration coverage.
- Local lease-6 evidence: the red-first ownership contract rejected the stale
  Mobile notification 0010 setup, then passed; all 10 migration-readiness static
  tests passed; portal-data full ran 320 tests successfully with 160 expected
  PostgreSQL skips. Hosted PostgreSQL 15/16 remains required for current ORM/0011
  metadata integration.

## Hosted and external limits

- Local isolated PostgreSQL was unavailable, so the new real-transaction lock
  regression plus PostgreSQL 15.8/16.4 migration, metadata diff, compatibility,
  concurrency, and exact rollback-harness behavior remain for hosted CI. The
  test-only 0011 reversal is restricted to the isolated test database and exact
  known revisions; production migration downgrade still preserves evidence.
- No notification provider, cloud, Secret, deployment, production database,
  runtime, or real user/data mutation occurred. Production schema/runtime rollout
  and any real notification remain separate Owner gates.
