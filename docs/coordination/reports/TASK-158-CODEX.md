# TASK-158 Codex writer report

## Delivered

- Added principal-scoped Event list/detail reads backed only by the immutable
  `event_invitees.included` snapshot for active people.
- Limited the projection to non-ended `published` and `cancelled` Events with
  ordered Activities; linked Game IDs are returned only when the same principal
  can already read that Game.
- Added Mobile API `events:read`, `/events`, `/events/{event_id}` and the bounded
  OpenAPI contract without exposing invitees, eligibility, manager, audit, or PII.
- Added production-shaped Flutter Event list/detail/timeline UI with linked-Game
  navigation and explicit loading, empty, error, cancelled, and offline-unavailable
  states. No cache schema was changed.

## Verification

- Mobile API focused and OpenAPI/shared service tests: `50/50` passed.
- `python -m unittest discover -s apps/mobile_api/tests -v`: `47/47` passed.
- `python -m unittest discover -s shared_lib/tests -v`: `54/54` passed.
- `python -m unittest tests.portal_data.test_phase_c_lifecycle -v`: 3 non-database
  tests passed; 29 PostgreSQL tests skipped because the local PostgreSQL environment
  was unavailable. Hosted PostgreSQL 15/16 remains required.
- Flutter focused tests (`integration_test.dart`, `basic_app_test.dart`): `147/147`
  passed; focused `flutter analyze` reported no issues.
- Repository formatter API reported no Python file requiring Black changes after
  the Windows Black CLI stalled as covered by `AGENTS.md`.
- `git diff --check` passed; exact scope and status were reviewed before commit.

## Remaining gates

- Hosted PostgreSQL 15/16, Mobile API, and Flutter gates plus independent L3
  acceptance are required before merge.
- Runtime grants for the existing Event tables remain a deploy gate. No schema,
  migration, deploy, cloud, Secret, IAM, production data, notification, or runtime
  mutation was performed.

## Reviewer correction evidence

- Lease 2 aligned Event, Activity, and linked Game wire IDs with the exact opaque
  signed-bigint contract and rejects malformed detail IDs before transport.
- Event list/detail now route terminal authentication through the canonical root
  callback and fence completions by both session generation and principal scope.
- Exact `dart format` completed with exit 0 on the four affected Dart files;
  final focused Flutter tests passed `152/152` and focused analyze found no issues.
