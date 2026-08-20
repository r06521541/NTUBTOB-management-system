# TASK-122: Flutter staging principal projection observability

task_type: work_package
delivery_group: mobile-staging-officer-acceptance
requires_independent_pr: false
status: ready_for_codex
base_commit: bd144e28e527959c15d7a9eb7dae8d6cb69a08d6

## Goal

Resolve the TASK-119 staging source-runtime contradiction with a minimal,
privacy-safe debug-only principal projection in the real `BasicGamesView`.
The diagnostic must allow the staging acceptance operator to distinguish the
localized access role and whether attendance-report reading is enabled without
exposing identity or session data.

## Repository scope

- `clients/flutter_app/**` limited to the real Basic presentation and direct
  tests.
- One `TASK-122` Codex report and one Flutter Work review on the shared branch.
- No backend, shared library, OpenAPI, schema, deployment, Secret, IAM, LINE
  Console, notification, or production change.

## Invariants

- The existing report guard and capability behavior stay unchanged.
- The diagnostic is debug-only (`kDebugMode`) and absent from release
  presentation.
- It shows only one localized role label: `一般使用者`, `幹部`, or `系統管理者`,
  plus a localized report-read enabled/disabled boolean.
- It does not show Person ID, additional display data, raw capability strings
  or lists, endpoint/origin, token, provider subject, session, secure storage,
  or response body.
- It introduces no navigation, capability elevation, network request, cache
  mutation, attendance mutation, or notification behavior.

## Verification

- Direct tests cover all three localized role labels and report-read enabled
  and disabled values.
- Tests cover diagnostic absence in release-mode semantics through an injected
  diagnostic flag where testing global `kDebugMode` directly is impractical.
- Tests prove the diagnostic does not add navigation or alter the existing
  report capability guard.
- Run Flutter format, analyze, direct/full tests, `git diff --check`, writer
  scope, and no-sensitive-literal checks as available.

## Runtime sequence

1. After Domain acceptance and Main release, rebuild current main staging debug
   with the same signing and config, then install with `-r` to preserve current
   app data/session.
2. Perform exactly one cold start and observe only the debug diagnostic.
3. Do not re-login or mutate attendance. Stop on session loss or configuration
   ambiguity and report to Main Work.
4. The existing TASK-119 Officer report/offline acceptance remains read-only;
   restore to Basic and logout stay governed by Main's explicit runtime order.

## Execution checkpoint

1. Goal: make fresh staging role/report-read projection observable without exposing sensitive data.
2. Core files: BasicGamesView, direct widget tests, TASK-122 report/review lane.
3. Invariants: debug-only, localized aggregate values only, unchanged guard and no new side effect.
4. Tests: three roles, enabled/disabled report read, release absence, no navigation/elevation.
5. Blocker: runtime remains blocked until Main releases the post-acceptance rebuild and cold-start sequence.
