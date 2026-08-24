# TASK-157 Flutter account and notification experience incubator

## Classification

- task_type: work_package
- risk: incubator L1/L2-local (presentation, route composition, session-local draft)
- incubator_delivery_group: `flutter-account-notification-experience-v1`
- shared_branch: `codex/flutter-account-notification-incubator`
- base: `b0c8cbb7ffd35950f366d289c7b70979f62b99fa`
- milestone: Owner can inspect a complete fake account-link/recovery journey and an officer unanswered-notification draft journey in the production demo
- requires_independent_pr: false
- owner_authorized: 2026-08-24

## Active writer claim

- claim_id: `task-157-flutter-writer-20260824`
- lease_version: 1
- actor_id: `task157_flutter_writer`
- role: `codex-writer`
- scope: account/recovery fake-demo UX, Officer unanswered-notification local draft, scoped shadcn presentation
- owned_paths: the paths listed below
- write: allowed only on `codex/flutter-account-notification-incubator`
- report_target: `docs/coordination/reports/TASK-157-FLUTTER-CODEX.md`
- stop_conditions: any real provider/notification call, API/auth/cache/schema or deployment boundary; overlapping unknown dirty files; inability to retain zero-transport demo invariant

## Product outcome

Deliver one coherent, user-friendly Flutter incubation slice that combines the
Owner's previously approved account and notification directions:

1. Present the existing Google/LINE sign-in, linked-method management and
   unknown-identity recovery flows as a clear step-by-step mobile journey.
   Include deterministic fake states for linked methods, candidate, fresh proof,
   explicit confirmation, cancellation, expiry/conflict and safe retry. Reuse the
   production identity-link controller and routes; do not change auth protocol,
   session lifecycle, API calls or security decisions.
2. Add an Officer-only unanswered-notification draft surface derived solely from
   the already loaded `AttendanceReport`. Show the exact unanswered count/list,
   local recipient selection, a small set of fictional message templates,
   editable session-local preview and explicit final confirmation preview.
   "Send" is a fake/demo-only local recording action: it must never call a real
   transport, notification provider or backend and must never claim delivery.
3. Apply a scoped `shadcn_flutter` visual layer to these account/recovery and
   notification-draft surfaces. Retain `MaterialApp`, Navigator, existing
   controllers, keys, semantics and portal navy/gold visual tokens. Do not replace
   navigation, inputs, dialogs or overlays globally.
4. Extend `ProductionDemoApp` with deterministic, discoverable scenarios for the
   account and notification flows, using production widgets and hard-rejecting
   transport/provider ports. The demo must remain available for repeat rendering
   by the existing Demo Launcher.

## Invariants and non-goals

- No API/OpenAPI/DTO, backend/shared library, schema/migration, durable cache,
  auth/session/capability rule or provider-verification change.
- No real LINE/Google sign-in, notification delivery, clipboard, external app,
  Secret, cloud, deployment, signing or store action.
- Account provider actions remain explicit taps; offline performs zero provider
  and identity-link transport calls. Pending review credentials never become
  recovery credentials.
- Notification recipients come only from the currently loaded authorized report;
  no lookup, guessing, hidden recipient expansion or persistence. The UI must say
  clearly that the draft is local and not sent.
- Preserve terminal/logout/person-switch route retirement and state cleanup.

## Owned paths

- `clients/flutter_app/pubspec.yaml`
- `clients/flutter_app/pubspec.lock`
- minimum affected files under `clients/flutter_app/lib/`
- corresponding focused files under `clients/flutter_app/test/`
- `docs/coordination/reports/TASK-157-FLUTTER-CODEX.md`

Do not modify Web/backend/shared/schema/deployment, coordination policy/state,
archive or PR #180 product/security behavior.

## Focused evidence

- identity-link/account widget tests for every deterministic state, explicit taps,
  retry, route retirement, offline zero-call and fake-provider zero side effects;
- Officer draft tests for exact unanswered derivation, selection/template/edit/
  confirm/cancel, per-game/session reset, capability guard and zero transport;
- production-demo tests for representative account and notification scenarios and
  `unexpectedTransportCalls == 0`;
- affected `flutter analyze`, canonical Dart format, `git diff --check`, final
  branch/HEAD/status;
- one fake debug APK only when the first render-ready generation is reached.

## Incubator exit conditions

Stop and return to Main before adding a real notification-send endpoint, changing
auth/API/cache/schema/provider/platform configuration, invoking a real provider,
or requiring Secret/deployment/signing. Commit and push descriptive checkpoints
to the shared incubator branch; do not create a PR or run hosted CI before an
Owner-declared delivery milestone.
