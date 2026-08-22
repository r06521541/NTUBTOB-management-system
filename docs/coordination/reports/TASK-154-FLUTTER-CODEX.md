# TASK-154 Flutter Codex evidence

## Delivered

- Added a session-local decision summary derived only from the loaded attendance
  report and current draft: starters out of nine, missing starters, bench and
  unanswered counts, with distinct warning and calm ready states.
- Added independent, initially empty fine-position and nine-slot batting-order
  state. Each batting slot selects only a fine-eligible player who already has a
  position; moving a player between slots removes the old slot, removing their
  position clears their batting slot, and DH excludes P.
- Added Web-parity coarse/fine planning: coarse pitcher/catcher/infield/outfield
  grouping; fine P/C/1B/2B/3B/SS/LF/CF/RF/DH field assignment; unique-player
  enforcement; late/early annotations from the live loaded report; and the
  DH/non-batting-pitcher rule.
- Added labelled, accessible move-up, move-down, move-to-bench and add-to-lineup
  actions. Boundary and full-lineup actions remain visible with explanatory
  tooltips while disabled.
- Coarse reset, fine reset and clear-all each require explicit session-only
  confirmation. Their state boundaries match Web: coarse reset does not touch
  fine, fine reset does not touch coarse, and clear-all clears both.
- The draft de-duplicates the attending pool and independently prevents duplicate
  field and batting assignments while preserving session/back and per-game
  ownership behavior.
- Deterministic production demo covers thin and ten-player reports as truthful
  empty fine drafts, unanswered warning, early/late annotations and stale
  offline use with zero transport. Focused draft evidence separately proves the
  complete-nine ready state.
- Added readable coarse/fine summary previews and an explicit-tap copy action
  behind an injectable port. Tests use a recording fake and never touch the real
  device clipboard; no print or external app is invoked.

## Contract gaps kept explicit

- The Mobile report has no `member_id` or coach-eligibility field. Coach controls
  are visibly disabled with an explanation; access level and names are never
  used as substitutes.
- Reply annotations are carried session-locally from fresh authorized report
  reads. Existing durable cache encoding is unchanged, so a reconstructed cache
  that lacks reply detail marks fine-position eligibility unavailable instead
  of guessing.

## Focused evidence

From `clients/flutter_app` with the repository Flutter 3.47 / Dart 3.13 wrapper:

- `flutter test test/officer_prereview_test.dart` — pass, 37 tests.
- `flutter test test/production_demo_test.dart` — pass, 16 tests.
- `flutter analyze lib/officer_prereview.dart lib/production_demo.dart test/officer_prereview_test.dart test/production_demo_test.dart` — pass, no issues.
- Canonical `dart format` followed by `dart format --output=none --set-exit-if-changed` on the same affected Dart files — pass.
- `git diff --check` — pass.

No full Flutter suite, hosted CI, emulator, platform build, Web change,
API/auth/cache encoding change, device storage, print/external export, official
lineup submit, provider call, deployment or real data mutation was performed.
