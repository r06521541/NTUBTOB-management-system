# TASK-156 Mobile Lineup member-number contract parity

## Classification

- task_type: work_package
- risk: L3 API/shared contract + L2 Flutter cache/presentation
- delivery_group: `mobile-lineup-member-number-v1`
- implementation_branch: `codex/task-156-lineup-member-number`
- owner_authorized: 2026-08-23
- schema_or_migration: none
- production_or_real_data: none

## Execution checkpoint

- Goal: expose existing Member numbers through the authorized attendance report and complete Web-equivalent session-local coach/number Lineup behavior.
- Core files: portal-data report projection, Mobile API service/OpenAPI/tests, Flutter integration/report cache/Lineup/demo/tests.
- Invariants: report capability + scoped Game authorization stay unchanged; no `member_id`; any attending candidate may be coach; Lineup remains session-local only.
- Minimum evidence: backend service/consumer/OpenAPI suites, shared library rebuild/install, Flutter focused/adjacent tests + analyze/format/diff, hosted affected gate before integration.
- Ambiguity/blocker: none; Member number is existing nullable data and no schema is authorized.

## Product and contract outcome

1. Add nullable `member_number` to each `AttendanceReportPerson` projection.
   Source it only from the already joined active Member row. Do not expose
   `member_id`, identity/provider data, contact data or a coach eligibility flag.
2. Update the canonical Mobile API service, OpenAPI schema/examples and direct
   producer/consumer/security tests. Existing clients that omit the new optional
   field must remain valid; malformed type/range values fail the Flutter contract.
3. Carry the optional number through Flutter integration and the principal-
   scoped Officer report cache using a backward-compatible optional encoding.
   Missing legacy/offline data stays usable and simply omits the number.
4. Display `#<number>` consistently beside a player's name in Officer report
   Lineup candidate controls, defensive positions, batting order, reserves and
   copied coarse/fine summaries. Never invent a number.
5. Remove the disabled coach-eligibility placeholder. Coarse and fine modes each
   allow any attending Lineup candidate to toggle coach independently, matching
   Web state semantics. Coach selection does not remove the person from field or
   batting eligibility. Coarse reset clears coarse roles/coaches only; fine reset
   clears fine positions/batting/fine coaches only; clear-all clears both.
6. Preserve Web-exact reply eligibility: attending/early-leaving may enter fine
   positions; late arrivals remain coarse-only. Preserve all TASK-154 uniqueness,
   DH/non-batting-pitcher, confirmation, per-game session and offline invariants.
7. Lineup remains deliberately session-local. Do not add read/save/submit,
   version, concurrency, audit, cross-device or durable Lineup state.

## Focused evidence

- repository/service tests prove Member number projection, nullable absence,
  stable sorting, authorization/redaction and no new query-per-person behavior;
- OpenAPI producer/consumer contract tests cover optional nullable integer;
- Flutter parser rejects malformed numbers and accepts omitted/null values;
- cache round-trip and legacy payload tests preserve/omit number correctly;
- Lineup direct/widget tests cover numbers in UI/summary and independent coarse/
  fine coach toggles/reset boundaries without affecting field/batting state;
- production demo uses fictional numbers and production widgets;
- rebuild/install shared library, affected Python suites, Flutter focused tests,
  analyze/format, `git diff --check`, final status and exact HEAD.

Hosted affected CI and independent API/auth/privacy + Flutter lifecycle review are
required before final integration. No PostgreSQL matrix because no model/schema/
migration changes; no emulator/platform build unless a concrete UI defect needs it.

## Stop conditions

Stop before schema/model/migration, production DB/data, deployment, Secret/IAM,
real notification/provider, auth/capability expansion, `member_id` exposure,
official Lineup persistence/submission, dependency or platform configuration.

## File boundary and handoff

Modify only the minimum required backend/shared contract files, Flutter files and
tests, plus `docs/coordination/reports/TASK-156-CODEX.md`. Do not modify Web Portal,
policy, archive or deployment files. One writer implementation branch, one batched
correction round if needed, and one final PR for this delivery group only.
