# TASK-153 Flutter Codex evidence

## Delivered

- Extended the existing authorized schedule discovery with accessible Month,
  Week and Agenda presentations backed only by the already-loaded games.
- Added session-local selected day, previous/next period and Today controls.
  Presentation, day, search, location filter and scroll state survive opening an
  authorized game detail and returning.
- Month renders a deterministic Monday-first 42-day grid with filtered game
  counts and a selected-day list. Week renders Monday-to-Sunday sections, while
  Agenda retains the chronological grouped list.
- Existing team/location search and location-presence filters project through
  every presentation. A day with no loaded games is distinct from a day whose
  loaded games do not match active search or filters.
- Local calendar grouping uses each loaded game's existing `startAt.toLocal()`
  value. Offline retains stale/read-only wording, opens loaded cached detail and
  performs no transport or mutation.
- Deterministic production demo data covers multiple months, two games on one
  day, a Monday week boundary, selected-day empty/no-match and offline use with
  production widgets.

## Focused evidence

From `clients/flutter_app` with the repository Flutter 3.47 / Dart 3.13 wrapper:

- `flutter test test/task153_schedule_test.dart` — pass, 5 tests.
- `flutter test test/production_demo_test.dart` — pass.
- `flutter analyze lib/basic_app.dart lib/production_demo.dart test/task153_schedule_test.dart test/production_demo_test.dart` — pass, no issues.
- Canonical `dart format` followed by `dart format --output=none --set-exit-if-changed` on the same affected Dart files — pass.
- `git diff --check` — pass.

No full Flutter suite, hosted CI, emulator, platform build, API/auth/cache
change, device-calendar permission, export, external deep link, provider call,
deployment or real data mutation was performed.
