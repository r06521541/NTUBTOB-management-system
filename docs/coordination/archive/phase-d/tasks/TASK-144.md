# TASK-144: Production-shaped Flutter fake demo

- Task type: delivery
- Delivery group: `flutter-production-shaped-demo`
- Risk level: L2
- Base: `c3baebddd08a100efafac47b641c129d956f68c7`
- Owner gate: none

## Role claim

- claim_id: `task-144-flutter-writer`
- lease_version: 1
- actor_id: `01a013a7-7fde-7363-9314-7a255e8206a5`
- role: `codex-writer`
- scope: make development fake mode render the production Flutter widgets with deterministic fictional data
- owned paths:
  - `clients/flutter_app/lib/main.dart`
  - `clients/flutter_app/lib/production_demo.dart`
  - `clients/flutter_app/test/production_demo_test.dart`
  - `clients/flutter_app/README.md`
  - `docs/coordination/reports/TASK-144-FLUTTER-CODEX.md`
- write: true, limited to the owned paths
- report_to: `main-work`
- stop_only_on: production real-mode behavior change, required change outside owned paths, any network/native-login/secure-storage dependency, unavailable exact Flutter toolchain, or a failing invariant that cannot be corrected within one bounded round

The same `claim_id` and `lease_version` may be acknowledged only once and must
not restart work or verification. No Domain Work is assigned unless the final
diff changes the real-mode auth/session/cache/authorization path.

## Goal

Make the existing one-command development fake mode a truthful visual preview
of the current product by composing the same production game list, detail,
attendance, account-status and Officer report widgets with deterministic
fictional adapters.

## Scope and invariants

- `CLIENT_MODE=fake` launches a visibly fictional production-shaped demo rather
  than the separate legacy `DemoApp` shell.
- Reuse production widgets directly; do not copy their layout or business logic
  into parallel demo widgets.
- Provide deterministic in-app scenarios for Basic/Officer, online/offline and
  populated/empty/error presentation. Scenario controls may be demo-only but
  must be clearly labelled as fictional.
- Production-shaped detail and Officer report navigation must work using only
  injected in-memory fake transport/cache/session data.
- Fake mode must not instantiate HTTP transport, native LINE login, platform
  secure storage, staging configuration or any external side effect.
- Real-mode composition, API/auth/session/cache/attendance authorization and
  production compile-time configuration remain byte-for-byte unchanged except
  for selecting the new fake root in `main.dart`.
- Keep the existing command:
  `flutter run --dart-define=APP_FLAVOR=development --dart-define=CLIENT_MODE=fake`.

## Verification budget

- Writer: early composition/security self-review; package-context formatter on
  owned Dart files; Flutter analyze; focused production-demo and existing
  `basic_app_test.dart` tests only.
- Main Work: one cumulative diff/invariant review; Domain only if the real-mode
  boundary changed.
- Hosted CI: one final change-selected Flutter gate after Main acceptance.
- Correction budget: one bounded round. No staging, LINE login, Secret,
  acceptance harness or production runtime gate.

## Acceptance

- The documented fake command boots the production-shaped fictional root.
- Basic and Officer scenarios visibly use current production widgets and can
  reach game detail; Officer can reach the read-only report surface.
- Online/offline plus populated/empty/error scenarios are deterministic and do
  not require credentials or network.
- Tests prove fake mode cannot cross into real HTTP/native-login/secure-storage
  composition and that real mode still selects `BasicBootstrapApp`.
- Existing focused production widget tests remain green.

## Delivery status

- Main review: accepted at `60fb936f4d87026aa518c035f00b76bd04d7b223`.
- Writer evidence: Flutter 3.47.0 / Dart 3.13.0; formatter clean;
  `flutter analyze` passed; focused demo 7/7 and existing Basic 64/64 passed.
- Main independently reviewed the cumulative five-path diff and confirmed the
  real-mode branch remains `BasicBootstrapApp(config: config)`, the demo reuses
  the production surfaces, and fake composition has no real transport, native
  login, secure-storage, staging-config or external-effect path.
- Status: `ready_for_hosted_ci`. The only remaining product gate is one
  change-selected hosted Flutter run followed by merge; no Domain or runtime
  gate is required for this diff.
