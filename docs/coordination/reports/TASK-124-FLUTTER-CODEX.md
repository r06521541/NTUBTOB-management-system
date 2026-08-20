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

## Producer package 2 delta: report-state observability

- Base: `1bc95656d5b8f197f71650331438aaadc6051f4c`
- Branch: `codex/task-124-report-state`
- Scope: canonical Officer report-state observability only

The report controller now records a mutually exclusive fresh-server or
offline-cache load provenance. The debug-only report projection is emitted only
when provenance, view state, report shape, and exactly zero enabled write
controls resolve to one canonical state: `ready`, `empty`, or
`offline_cached_readonly`. Missing, directly injected, conflicting, or nonzero
write-control inputs produce no canonical projection. The projection contains
no row, person, game, response-body, or cache-key material.

The existing capability checks, report navigation, and read-only behavior are
unchanged. Rendering remains hard-gated by `kDebugMode && diagnosticEnabled`;
injection can disable diagnostics but cannot enable them in release.

Verification delta:

- Tests-first red run failed on the intentionally absent diagnostic API.
- `flutter test test/officer_prereview_test.dart --no-pub`: passed, 28 tests.
- `flutter analyze --no-pub`: passed with `No issues found` after removing one
  unnecessary non-null assertion reported by the first analyze run.
- `flutter test --no-pub`: passed once, all 116 tests.
- `dart format` was limited to the two owned Dart files.

Dependency setup used the existing Flutter 3.47.0 / Dart 3.13.0 toolchain and
local package cache via `pub get --offline`. No app network, runtime, emulator,
login, staging, or application-cache mutation was performed. No release
artifact was built; release absence is covered by the hard-gate contract test,
not an artifact negative scan.

## Producer package 3 delta: authoritative own-reply observability

- Base: `ef5d9d47f8cc71ee0d34f187df51c75d3f1f52e8`
- Branch: `codex/task-124-report-state`
- Scope: bounded authoritative attendance own-reply observability only

Game detail now keeps local chip selection separate from the bounded
authoritative reply and its mutually exclusive source. A successful fresh
attendance GET records `fresh_server_get`; a successful mutation followed by
the existing attendance readback records `mutation_readback`. The projection
uses only the canonical reply vocabulary. Missing or conflicting provenance,
a non-ready view, pending or uncertain mutation, cached/offline state, and
direct injection all fail closed without an authoritative claim. An
authoritative nullable server reply is projected as the bounded token `none`.

The existing submit, reconcile, idempotency, capability, and navigation
behavior is unchanged. Rendering remains hard-gated by
`kDebugMode && diagnosticEnabled`; injection can disable diagnostics but cannot
enable them in release. The projection contains no person, game, row, response
body, idempotency key, token, cache key, or storage material.

Verification delta:

- Tests-first red run failed on the intentionally absent projection API.
- `flutter test test/basic_app_test.dart --no-pub`: passed, 41 tests.
- `flutter analyze --no-pub`: passed with `No issues found`.
- `flutter test --no-pub`: passed once across packages 2 and 3, all 120 tests.
- `dart format` was limited to the two owned Dart files.

Verification used the existing Flutter 3.47.0 / Dart 3.13.0 toolchain and
local package cache. No app network, runtime, emulator, login, staging, or
application-cache mutation was performed. No release artifact was built;
release absence is covered by the hard-gate contract test, not an artifact
negative scan.

### Package 3 review correction: authoritative no-reply state

Main review identified that a successful fresh attendance GET with
`own_reply=null` is authoritative evidence of not yet replied. The bounded
canonical observation now includes `none` alongside the five existing reply
wire values. Fresh GET always records `fresh_server_get`, including null;
successful mutation readback likewise preserves authoritative null as `none`.
The resolver still emits nothing for missing or conflicting provenance.

Correction verification:

- Tests-first focused run failed on the intentionally absent `none`
  observation.
- `flutter test test/basic_app_test.dart --no-pub`: passed, 42 tests.
- `flutter analyze --no-pub`: passed with `No issues found`.
- No unrelated or full suite was rerun for this focused correction.

## Producer package 4 delta: cache/session aggregate vocabulary

- Base: `23c99e84c9b7a15fbade236e77d121b05e39abc3`
- Branch: `codex/task-124-cache-session`
- Scope: bounded cache/session aggregate vocabulary only

Added a de-identified `CacheSessionAggregate` resolver. It emits exactly four
boolean observations: session presence, Basic cache presence, Officer report
cache presence, and pending attendance-intent presence. Every input is
required; pending intent is bounded to zero or one. Missing, negative, or
multi-intent observations resolve to no projection, so they cannot be
misrepresented as purge evidence.

Added the debug cache/session projection renderer with the same hard
`kDebugMode && diagnosticEnabled` gate used by the existing client evidence.
Its output contains only the four allowlisted `present`/`absent` tokens: no
storage key, principal, session/provider identity, token, body, path, or cache
value. An injected flag cannot enable rendering in a release build.

This vocabulary deliberately does not alter session, cache, mutation,
authorization, navigation, or wire behavior. It makes only a fully supplied,
bounded aggregate eligible for a future launcher consumer; incomplete local
state remains fail-closed rather than inventing a physical-purge claim.

Verification delta:

- Tests-first red run: focused integration test initially failed because the
  aggregate API did not exist.
- `flutter test test/integration_test.dart --no-pub`: passed, 40 tests.
- `flutter test test/basic_app_test.dart --no-pub`: passed, 43 tests.
