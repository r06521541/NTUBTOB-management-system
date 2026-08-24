# TASK-156 Codex report

- Branch: `codex/task-156-lineup-member-number`
- Base: `a98883e3615ac8a8cef5084fc0c9aa889ea82da7`
- Scope: existing nullable Member number projection plus session-local Flutter Lineup parity; no schema, migration, Web, deployment, production or real-data change.

## Delivered

- Portal-data's existing joined Member row now contributes nullable `member_number` to the authorized attendance report without adding queries or exposing `member_id`.
- Mobile API and canonical OpenAPI carry optional nullable small-integer member numbers while preserving report authorization, Game scoping, redaction and query bounds.
- Flutter accepts omitted/null numbers, rejects malformed/out-of-range values, and preserves numbers through the principal-scoped durable report cache without breaking legacy cache payloads.
- Lineup candidate controls, positions, batting order, reserves and copied summaries display real `#<number>` labels only when present.
- Any attending candidate can independently toggle coarse and fine coach state. Coarse/fine/all reset boundaries clear only their respective coach and lineup state; coach state does not alter field or batting eligibility.
- Fictional production demo data uses deterministic member numbers through production widgets; Lineup remains session-local and offline read-only.

## Verification

- Backend shared/Mobile API/OpenAPI focused suite: 42 passed.
- Rebuilt and installed `shared_lib-0.0.1`; installed Mobile API/OpenAPI consumer suite: 26 passed.
- Flutter `officer_prereview_test.dart` + `production_demo_test.dart`: 54 passed.
- Flutter analyze on affected implementation/tests: no issues.
- Dart format check on affected implementation/tests: unchanged.
- Python `compileall`: passed after using the required writable execution boundary.
- OpenAPI JSON parse: passed.
- No external application, database, notification, cloud, deployment or production effects occurred.

## Consolidated correction round

- Correction base: `a61dd7667099835d280777ccb60c6db18bef36fa`.
- Canonical `member_number` product range is now `0..999` in OpenAPI, Flutter wire parsing and durable-cache validation, with boundary/malformed regressions.
- A focused `IdentityLifecycleRepository.game_attendance_report` PostgreSQL regression covers joined number projection, nullable no-Member projection, Basic API `member_id` redaction and the fixed four-query boundary. The local run skipped the configured-database class because no isolated PostgreSQL URL was present.
- The canonical Flutter adapter now preserves both reply and member number for `not_attending`; number/null/omitted inputs are covered through direct API mapping and durable-cache round trips. New cache writes preserve reply while legacy payloads with omitted reply remain readable.
- Focused Python unittest run: 54 run, `OK` (27 configured-PostgreSQL skips); installed direct Mobile API consumer suite: 37 passed.
- Focused Flutter `integration_test.dart` + `officer_prereview_test.dart`: 88 passed.
- Flutter analyze: no issues; Dart format check, Python Black check, Python compileall, OpenAPI JSON/range assertion and `git diff --check`: passed.
- Local external effect: rebuilt and reinstalled `shared_lib-0.0.1` only in the bundled Codex Python runtime. No database, notification, cloud, deployment, production or real-data effect.
