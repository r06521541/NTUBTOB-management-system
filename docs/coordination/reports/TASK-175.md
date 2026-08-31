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
  and identity-approval surfaces no longer grant guest-player state.
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
  241 passed.
- `py -3.10 -m unittest discover -s tests/portal_data -v`: 306 passed,
  154 expected skips without the isolated PostgreSQL URL.
- Flutter focused tests: 175 passed.
- Flutter analyze on the five affected files: no issues; Dart format check changed
  zero files.
- Python compileall over the migration, shared library, Mobile API, Web Portal,
  portal-data tests, and migration readiness tools: passed.
- Pinned Black formatter API comparison and isort checks on affected Python files:
  passed. Broad Black CLI was terminated after its known Windows high-CPU stall;
  no formatter process was left running.

## Hosted and external limits

- Local isolated PostgreSQL was unavailable, so PostgreSQL 15.8/16.4 migration,
  concurrency, and exact rollback-harness behavior remain for hosted CI. The
  test-only 0011 reversal is restricted to the isolated test database and exact
  known revisions; production migration downgrade still preserves evidence.
- No notification provider, cloud, Secret, deployment, production database,
  runtime, or real user/data mutation occurred. Production schema/runtime rollout
  and any real notification remain separate Owner gates.
