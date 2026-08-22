# TASK-154 Lineup Lab decision-quality incubator

## Classification

- task_type: work_package
- risk: incubator L1 (derived presentation/session-local draft only)
- incubator_delivery_group: `flutter-member-experience-incubator-v1`
- shared_branch: `codex/flutter-incubator-member-experience`
- requires_independent_pr: false
- owner_authorized: 2026-08-23

## Product outcome

Improve the existing Officer-only, session-local Lineup Lab so it supports an
actual pre-game decision instead of exposing raw lists:

1. Add a decision summary derived only from the loaded report/draft: starting
   lineup count out of nine, missing starter count, bench count and unanswered
   count. Fewer than nine starters is an explicit warning; zero unanswered and
   a complete nine-person lineup use a calm ready state. Offline/stale source
   wording remains visible and no forecast or certainty is invented.
2. Follow the Web Portal Lineup Lab's useful hierarchy: nine explicit batting
   slots, clear mode switching, candidate selection and warning/danger visual
   language. Do not copy Web-only defensive-position/coarse-role data because
   the Mobile report does not contain that contract.
3. Improve mobile interaction with a clear `棒次` / `候補` segmented mode (with
   counts), numbered starter cards/slots, labelled move-up, move-down and move-
   to-bench actions, and an equally clear add-to-lineup action for bench players.
   Disabled boundary actions must remain understandable and accessible.
4. Empty starter slots up to nine must remain visible so the gap is concrete.
   A full lineup may still place additional attending people on the bench; no
   duplicate person may appear across starters/bench.
5. Reset requires an explicit confirmation dialog describing that only this
   session-local draft will be reset. Cancel preserves the exact draft; confirm
   restores the deterministic attending-only default.
6. Preserve all TASK-151 guarantees: attending-only pool, system/back return
   preservation, per-game session scope, game-change reset, no official submit,
   no persistence/export/share and offline zero transport/mutation.
7. Extend deterministic production demo coverage for fewer-than-nine,
   complete-nine-with-bench, unanswered warning, reset cancel/confirm and
   offline stale cases using production widgets.

## Web reference boundary

Use `apps/web_portal/templates/lineup_lab.html` and the shared warning/danger,
selected-state and action hierarchy in `apps/web_portal/static/brand.css` as
product references. Flutter may improve the mobile information architecture,
but must not add Web-only coach/position/field assignment, copy/print behavior,
localStorage compatibility or an official server-side lineup contract.

## Focused evidence

- unit tests for missing-to-nine, bench/unanswered counts, ready/warning state
  and no-duplicate invariant after every operation;
- widget tests for segmented mode/counts, nine visible slots, readable labelled
  up/down/bench/add actions and disabled boundaries;
- reset cancel preserves the exact draft; reset confirm restores default;
- existing system-back persistence and new per-game reset regressions remain;
- offline warning/zero transport and deterministic production-demo scenarios;
- affected `flutter analyze`, canonical Dart format, `git diff --check` and
  final `git status --short`.

No task-local full suite, hosted CI, emulator or platform build. Commit/push a
descriptive checkpoint only; PR remains deployment/release-candidate gated.

## Incubator exit conditions

Stop before changing API/OpenAPI/DTO, auth/session/capability, durable cache,
backend/shared/schema/data, real notification/provider, device storage/export,
official lineup submission, Web localStorage compatibility, defensive position
data, deployment/signing/store behavior or external deep link.

## File boundary and handoff

Modify only the minimum required `clients/flutter_app/**` files and create
`docs/coordination/reports/TASK-154-FLUTTER-CODEX.md`. Do not modify task,
HANDOFF, policy, backend, Web Portal, archive or deployment files. Commit/push a
descriptive shared-branch checkpoint; no PR. Proactively report exact base/HEAD,
status, changed files, focused evidence, compromises and external effects.
