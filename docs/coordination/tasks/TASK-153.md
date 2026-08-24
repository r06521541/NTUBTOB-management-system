# TASK-153 Schedule calendar presentations incubator

## Classification

- task_type: work_package
- risk: incubator L1 (presentation/navigation/local state only)
- incubator_delivery_group: `flutter-member-experience-incubator-v1`
- shared_branch: `codex/flutter-incubator-member-experience`
- requires_independent_pr: false
- owner_authorized: 2026-08-23

## Product outcome

Extend the existing authorized, locally loaded schedule discovery into calendar
presentations without adding transport, persistence or external integration:

1. Add an accessible presentation switch for Month, Week and Agenda views.
2. Month shows a navigable calendar grid with truthful per-day game indicators,
   selected-day emphasis and a selected-day game list. Week shows the selected
   local calendar week with day lanes/sections and useful game summaries.
   Agenda keeps the existing chronological grouped-list strength.
3. Support previous/next period, Today and explicit day selection. Month/week/
   selected day are session-local and survive opening an authorized game detail
   and returning.
4. Existing team/location search and location filters apply consistently to all
   three presentations. Distinguish no games on a selected day from no matches
   under active search/filter.
5. Derive local calendar dates from each authorized Game `startAt`; handle month
   boundaries, year boundaries, local week starts and multiple games per day
   deterministically. Do not invent timezone data beyond existing local-time
   conversion.
6. Offline uses only the same principal-scoped loaded games, retains stale/read-
   only wording and performs zero transport/mutation.
7. Extend deterministic production demo coverage for multi-month, multi-game
   day, week boundary, selected-day no-game/no-match and offline views using the
   production widgets.

No calendar export, device-calendar permission, URL/deep link, external app or
background reminder is permitted.

## Focused evidence

- unit tests for month grid boundaries, local week range, date grouping and
  filtered per-day counts;
- widget tests for Month/Week/Agenda switching, previous/next/Today, selection,
  no-game versus no-match and detail-return state preservation;
- tests proving search/location filters affect every presentation consistently;
- offline zero-transport and stale/read-only widget evidence;
- deterministic production-demo composition for the named calendar cases;
- affected `flutter analyze`, canonical Dart format, `git diff --check` and
  final `git status --short`.

No task-local full suite, hosted CI, emulator or platform build. Descriptive
checkpoint commit/push only; PR remains deferred until Owner declares a
deployment-adjacent or release-candidate gate.

## Incubator exit conditions

Stop and notify Main before changing API/OpenAPI/DTO, auth/session/capability,
durable principal cache, backend/shared Python, schema/data, Secret/IAM, real
provider/notification, deployment/signing/store behavior, device calendar,
calendar permission, export or external deep link.

## File boundary and handoff

Modify only the minimum required `clients/flutter_app/**` files and create
`docs/coordination/reports/TASK-153-FLUTTER-CODEX.md`. Do not modify task,
HANDOFF, policy, backend, archive or deployment files. Commit/push a descriptive
checkpoint to the shared branch; no PR. Proactively report exact base/HEAD,
status, changed files, focused evidence, compromises and external effects.
