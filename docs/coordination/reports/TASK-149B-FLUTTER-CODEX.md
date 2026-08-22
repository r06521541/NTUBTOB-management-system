# TASK-149 Slice B Flutter Codex report

- Branch: `codex/task-149b-flutter-parity-writer`
- Base: `f724a9b7a15d0f5eec5916d3b35165113b61b790`
- Scope: Flutter phase-one parity and fictional production-shaped demo only; no backend/shared contract, schema, provider, deployment, Secret/IAM, signing, store, or production mutation.

## Delivered

- Self display-name edit uses one persisted idempotency key per logical intent. Unknown network outcomes retain the intent/key for same-payload retry. A successful canonical Person refresh reconciles the root projection, principal cache, report/notification capability partitions, and rejects stale lifecycle callbacks.
- A `202` LINE exchange produces only a memory-held review credential. The review client is independent of `SessionController`, can only read/append its own pending conversation, retains an append key across uncertain retries, and directs terminal/unavailable states to fresh normal login.
- The home list promotes the next authorized game and reads only that Person's own attendance online. Valid offline cache remains read-only and explicitly labels attendance as non-current; no cache does not render an authoritative empty home.
- Notifications load only the first page, support all/unread filters and explicit cursor load-more, and preserve epoch, terminal, cache, unread badge, read state, destination, offline, and single-flight boundaries.
- Installation-local onboarding is three pages and skippable. System/light/dark preference persists locally and applies immediately at the root. Permission/settings ports run only from explicit taps and no real provider is connected.
- Fictional demo scenarios for normal/offline/empty/error, pending review, notification paging, onboarding, and settings use the same production widgets with deterministic in-memory adapters and no credentials/network.
- Root `.gitignore` now ignores only `/lib/`; nested Flutter `lib/` files are trackable while repository-root `lib/` remains ignored.

## Verification

- `tools/Invoke-FlutterToolchain.ps1 flutter test test/foundation_test.dart test/integration_test.dart test/basic_app_test.dart test/notification_center_test.dart test/production_demo_test.dart test/officer_prereview_test.dart test/support_app_info_test.dart test/task149_slice_b_test.dart`: 196 passed.
- `tools/Invoke-FlutterToolchain.ps1 flutter analyze`: no issues.
- Two consecutive canonical `dart format` passes over nine affected Dart files: both reported `0 changed`; SHA-256 comparison after the second pass found zero changed files.
- `git diff --check`: passed (Git reports only the existing Windows LF-to-CRLF checkout warning for `.gitignore`).
- `.gitignore` regression: `git check-ignore --no-index clients/flutter_app/lib/local_preferences.dart` exited 1; `git check-ignore --no-index lib/task149-check.tmp` exited 0.

## External effects and limits

- No emulator, platform build, real LINE/API account, notification provider, cloud resource, database, deployment, signing, or store operation was used.
- Local-only tool effect: the repository wrapper resolved the already pinned Flutter dependencies using the configured Flutter 3.47.0 / Dart 3.13.0 toolchain.
- Hosted CI remains the full Flutter gate. Independent Domain/Main acceptance is still required; this writer did not self-accept.

## Handoff

- Next actor: `main-work` for composition/security review, then the assigned independent Flutter Domain review.
- Next action: review credential separation, profile lifecycle/cache reconciliation, pagination/filter concurrency, offline truthfulness, and explicit permission actions at the final commit HEAD.
