# TASK-124 Flutter producer package 1 report

- Base: `95f99a9a5778eea92b9d7e50ac0e1455cff90e1a`
- Branch: `codex/task-124-principal-freshness`
- Scope: principal freshness observability only

## Delivered behavior

- Added one mutually exclusive `PrincipalProvenance` state. A complete
  authenticated `/me` plus games load records `fresh_server`; reconstruction
  from `BasicCache` records `offline_cache`; missing direct-widget provenance
  projects bounded `unknown` and is non-authoritative.
- Extended the existing debug-only principal projection with only localized
  role, localized report-read enablement, and a bounded provenance token plus
  localized state. It does not project identity, raw capability, session,
  payload, origin, token, or storage material.
- Preserved the hard `kDebugMode && diagnosticEnabled` gate and the existing
  `person.canReadAttendanceReport` navigation guard. Offline cached Officer UI
  behavior is unchanged, but it cannot masquerade as `fresh_server` evidence.

## Verification

- Tests-first red run: focused test compilation failed on the intentionally
  absent provenance enum and constructor fields before implementation.
- `flutter test test/basic_app_test.dart`: passed, 37 tests.
- `flutter analyze`: passed with `No issues found`.
- `flutter test`: passed once, all 112 tests.
- `dart format` was applied only to the two owned Dart files.

The Windows `flutter.bat` wrapper stalled on its SDK lock path. Verification
used the same Flutter 3.47.0 / Dart 3.13.0 SDK through its
`flutter_tools.snapshot` entry point. Dependency setup used the existing lock
and cache with `pub get --offline`. No app network, runtime, emulator, login,
staging, or application-cache mutation was performed.

## Limits and handoff

- This package does not add report-state, attendance-reply, cache/session
  aggregate, launcher-consumer, release-artifact, device, or staging evidence.
- Main and reviewers remain read-only. The next actor is Work for delta-only
  acceptance of this shared task branch; no PR was created.
