# TASK-152 Flutter Codex evidence

## Delivered

- Added a member action dashboard that evaluates only the next five upcoming
  games already loaded for the current principal.
- Existing `attendance(gameId)` reads populate session memory only. Reads run
  in batches of at most three and duplicate in-flight game reads share one
  future.
- Session observations are scoped to the authenticated principal. A generation
  guard prevents delayed reads from writing after principal, connectivity or
  bounded-window changes.
- Pending means only a known `null` or `undecided` own reply. The dashboard
  shows the bounded count, nearest action, existing detail/reply flow, and full
  local schedule shortcut. Returning from detail refreshes only that game.
- Offline performs no attendance read. Unknown replies remain unknown and are
  explicitly excluded from the pending count.
- Deterministic production demo covers mixed replies, all resolved, retryable
  attendance error, offline unknown and no-upcoming states with production
  widgets.

## Focused evidence

From `clients/flutter_app` with the repository Flutter 3.47 / Dart 3.13 wrapper:

- `flutter test test/basic_app_test.dart --name "member action|action dashboard|offline unknown"` — pass, 8 tests.
- `flutter test test/production_demo_test.dart` — pass, 14 tests.
- `flutter analyze lib/basic_app.dart lib/production_demo.dart test/basic_app_test.dart test/production_demo_test.dart` — pass, no issues.
- Canonical `dart format` followed by `dart format --output=none --set-exit-if-changed` on the same affected Dart files — pass.
- `git diff --check` — pass.

No full Flutter suite, hosted CI, emulator, platform build, durable own-reply
storage, API/auth/cache change, provider call, deployment or real data mutation
was performed.
