# TASK-150 Flutter schedule discovery incubator

## Classification

- task_type: work_package
- risk: incubator L1 (UI/navigation/local state/fixtures only)
- incubator_delivery_group: `flutter-member-experience-incubator-v1`
- shared_branch: `codex/flutter-incubator-member-experience`
- requires_independent_pr: false
- owner_authorized: 2026-08-22

## Product outcome

Turn the authenticated member area into a coherent schedule-discovery flow
using only games already authorized and loaded by the current app:

1. Provide an obvious Home -> Schedule entry and a production schedule page.
2. Group loaded games by useful date sections and support local team/location
   search plus a small set of presentation filters. Empty and no-match states
   must be distinct.
3. Preserve the user's schedule view/filter/scroll context while opening an
   authorized game detail and returning during the same app session.
4. Offline mode may browse only the existing principal-scoped cached games,
   must remain read-only, and must visibly say the data may be stale.
5. Extend deterministic fake-demo scenarios with enough varied dates, teams,
   locations and empty/no-match cases to review the same production widgets.

The writer may reshape navigation, local view models and fixtures where that
improves the flow. Avoid broad visual-system rewrites unrelated to this flow.

## Milestone

Delivery group milestone is the first of:

- the complete Home -> Schedule -> search/filter -> Game detail -> back with
  preserved context flow is reviewable in normal, offline, empty and no-match
  demo scenarios;
- 3-6 substantive product commits accumulate across this group; or
- 2026-08-29.

TASK-150 is the first work package. It ends with a descriptive commit pushed to
the shared branch and Main's lightweight checkpoint review. It does not create
a PR or run hosted CI unless Main declares the milestone reached early.

## Focused evidence

- focused widget/unit tests for grouping, filtering, empty/no-match, navigation
  return-state and offline wording/zero mutation;
- affected `flutter analyze` and canonical Dart format check;
- necessary compile check for touched production composition;
- `git diff --check` and final `git status --short`;
- deterministic fake-demo composition test. No emulator or platform matrix by
  default.

Main reuses the exact-HEAD evidence, reviews the actual diff and product flow,
and does not rerun the full Flutter suite for this checkpoint.

## Incubator exit conditions

Stop and notify Main before changing any login/session/auth/capability rule,
backend or OpenAPI contract, shared Python boundary, durable principal cache
semantics, schema/data, Secret/IAM, real notification/provider, deployment,
signing or store behavior. Main must split or reclassify that work to L2/L3;
the incubator authorization does not permit it.

## File boundary

The writer may modify the minimum required files under
`clients/flutter_app/**` and create
`docs/coordination/reports/TASK-150-FLUTTER-CODEX.md`. Do not modify backend,
shared Python, task/HANDOFF/policy, archive, deployment or production files.

## Handoff

Commit and push to the shared incubator branch; do not create a PR. Report the
exact branch/base/HEAD, clean or known dirty state, changed files, focused
commands/results, product compromises and external effects. Completion or a
blocker must also be sent proactively to Main Work.
