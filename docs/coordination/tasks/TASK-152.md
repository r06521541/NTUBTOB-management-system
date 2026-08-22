# TASK-152 Member action home incubator

## Classification

- task_type: work_package and incubator milestone closer
- risk: incubator L1 (existing reads/navigation/session-memory presentation)
- incubator_delivery_group: `flutter-member-experience-incubator-v1`
- shared_branch: `codex/flutter-incubator-member-experience`
- requires_independent_pr: false
- owner_authorized: 2026-08-23

## Product outcome

Turn the authenticated member home into an action-oriented dashboard using
only games already authorized/loaded and existing per-game own-attendance reads:

1. Evaluate at most the next five upcoming loaded games and label that bounded
   scope truthfully. Do not present the result as an all-future-games count.
2. Show the number in that window whose own reply is absent or `undecided`, the
   nearest game needing action, and clear quick actions to reply/open detail or
   browse the full locally loaded schedule.
3. Reuse existing `BasicApi.attendance(gameId)` and existing detail/reply flow.
   Bound parallel attendance reads to at most three in flight, deduplicate the
   same in-flight/home-session reads, and avoid refresh loops.
4. Keep fetched own-reply observations in memory for this authenticated home
   session only. A successful reply/detail return may refresh the affected
   dashboard observation without adding durable storage.
5. Offline may show loaded principal-scoped games and only observations already
   known in the current session. Unknown reply state must say it cannot be
   confirmed offline; never infer pending from missing evidence.
6. Distinguish loading, actionable, all-known-resolved, partial/unknown, no
   upcoming game and retryable online failure states.
7. Extend deterministic production demo scenarios using the same production
   dashboard widgets with bounded-window, mixed-reply, all-resolved, offline
   partial/unknown and empty states.

The implementation may extract a focused session-local controller/view model.
Do not change existing API calls, DTOs, authentication, capability or durable
cache semantics.

## Milestone

TASK-152 is the third substantive product checkpoint in
`flutter-member-experience-incubator-v1`. After Main accepts its focused
evidence and actual delta, the delivery group reaches milestone: Main creates
one final PR for TASK-150/151/152, runs hosted Flutter CI and performs formal
integration acceptance. The Writer does not create the PR.

## Focused evidence

- unit tests for next-five selection, pending definition (`null` or
  `undecided`), nearest-action selection and honest bounded labels;
- deterministic concurrency test proving at most three attendance reads and
  no duplicate in-flight read;
- widget tests for actionable/all-resolved/partial-unknown/empty/error states
  and quick navigation;
- offline tests proving no transport and no pending inference from unknown;
- reply/detail return refreshes only the affected observation without loop;
- production-demo composition tests for the named scenarios;
- affected `flutter analyze`, canonical Dart format, `git diff --check` and
  final `git status --short`.

No task-local full suite, emulator or platform build. Main reuses exact-HEAD
focused evidence; hosted CI is deferred only until this checkpoint is accepted.

## Incubator exit conditions

Stop and notify Main before changing API/OpenAPI/DTOs, login/session/auth or
capability rules, durable principal cache/pending-intent semantics, backend or
shared Python, schema/data, Secret/IAM, real provider/notification, deployment,
signing or store behavior. Do not silently expand beyond five games or persist
own-reply observations. Such work must be split/reclassified L2/L3.

## File boundary

The Writer may modify the minimum required files under
`clients/flutter_app/**` and create
`docs/coordination/reports/TASK-152-FLUTTER-CODEX.md`. Do not modify backend,
shared Python, task/HANDOFF/policy, archive, deployment or production files.

## Handoff

Commit and push a descriptive checkpoint to the shared incubator branch; do
not create a PR. Proactively send Main exact branch/base/HEAD, clean or known
dirty state, changed files, focused commands/results, compromises and external
effects. Stop and report immediately on an exit condition or Git blocker.
