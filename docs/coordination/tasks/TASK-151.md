# TASK-151 Officer attendance insights and Lineup Lab incubator

## Classification

- task_type: work_package
- risk: incubator L1 (derived presentation/navigation/session-local draft only)
- incubator_delivery_group: `flutter-member-experience-incubator-v1`
- shared_branch: `codex/flutter-incubator-member-experience`
- requires_independent_pr: false
- owner_authorized: 2026-08-22

## Product outcome

Create one coherent Officer-only flow from the existing authorized single-game
attendance report into useful decision support and a local Lineup Lab:

1. Add an insights summary to the existing report: attending, unavailable and
   unanswered counts, response/availability proportions, and concise truthful
   callouts derived only from the loaded report. Small samples and offline data
   must be labelled; no prediction or invented certainty.
2. Let an authorized Officer open Lineup Lab from a ready report. Seed the
   available pool only from people in `attending`; never silently include
   `notAttending` or `notYetReplied`.
3. Support a session-local draft with ordered starting lineup/batting order and
   bench, including add/remove/reorder/reset. Names and ordering are planning
   aids only: show that the draft is not an official submitted lineup.
4. Preserve the draft while moving between insights and Lineup Lab within the
   same report route. Leaving the route or restarting may discard it; do not
   introduce durable storage.
5. Offline cached reports may use the same derived insights and local lab, but
   must retain stale/read-only source wording and perform zero transport or
   mutation.
6. Extend deterministic Officer demo scenarios so normal, offline, thin-roster,
   unanswered-heavy and empty states exercise the production widgets.

The writer may extract focused presentation models/widgets where useful. Do not
change capability definitions, report fetching/cache lifecycle, API DTOs or
server behavior.

## Milestone

This is the second substantive product checkpoint in
`flutter-member-experience-incubator-v1`. The delivery milestone remains the
first of:

- a reviewable Officer report -> insights -> Lineup Lab -> return flow across
  normal/offline/thin/empty scenarios;
- 3-6 substantive product commits in the delivery group; or
- 2026-08-29.

TASK-151 ends with a descriptive commit on the shared branch and Main's
lightweight checkpoint review. No task-specific PR or hosted CI is required.

## Focused evidence

- unit/widget tests for insight arithmetic and honest small/offline labels;
- widget tests proving capability-gated entry and attending-only pool;
- deterministic add/remove/reorder/reset and route-return draft preservation;
- offline tests proving zero transport/mutation;
- production-demo composition tests for the named scenarios;
- affected `flutter analyze`, canonical Dart format, `git diff --check` and
  final `git status --short`.

No full Flutter suite, emulator or platform matrix by default. Main reuses the
exact-HEAD evidence and reviews the actual delta and product boundary.

## Incubator exit conditions

Stop and notify Main before changing login/session/auth/capability rules,
attendance/report API or DTO contracts, durable principal cache semantics,
backend/shared Python, schema/data, Secret/IAM, real provider/notification,
deployment, signing or store behavior. Also stop before adding official lineup
submission, cross-device persistence, sharing/export or roster/position data
not already present in the authorized report. Main must split/reclassify such
work to L2/L3.

## File boundary

The writer may modify the minimum required files under
`clients/flutter_app/**` and create
`docs/coordination/reports/TASK-151-FLUTTER-CODEX.md`. Do not modify backend,
shared Python, task/HANDOFF/policy, archive, deployment or production files.

## Handoff

Commit and push a descriptive checkpoint to the shared incubator branch; do
not create a PR. Proactively send Main the exact branch/base/HEAD, clean or
known dirty state, changed files, focused commands/results, product compromises
and external effects. Stop and report immediately if any exit condition is
required.
