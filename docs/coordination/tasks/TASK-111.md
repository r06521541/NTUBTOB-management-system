# TASK-111：Flutter release identity and hosted CI baseline

task_type: delivery
delivery_group: flutter-release-identity-ci
requires_independent_pr: true
status: ready_for_codex
base_commit: 4792f529a374baa3f87386a0883a6a82c1ecb048

## Goal

Replace the generated fictional application identity with the Owner-approved
product identity and add a reproducible hosted Flutter gate. This task makes
future staging registration and client changes reviewable; it does not connect
to a real LINE channel, deploy an API or produce a signed release.

## Owner-approved identity

- User-facing Traditional Chinese name: `臺大校友比賽報你知`.
- Android application ID and namespace: `tw.org.ntubtob.portal`.
- iOS bundle identifier: `tw.org.ntubtob.portal`.
- iOS test bundle identifiers must derive from that bundle ID without colliding
  with the application target.
- The display name may change in a later product release. The package/bundle ID
  is treated as stable because LINE callbacks, device installation identity,
  signing and store records depend on it.

## Implementation scope

- Update Android namespace/application ID, `MainActivity` package/path and
  visible label. Keep `minSdk 24`, main `INTERNET`, backup exclusion and the
  unsigned release boundary from TASK-110.
- Update iOS app/test bundle IDs and display name. Preserve target 15 and the
  identifier-derived `line3rdp.$(PRODUCT_BUNDLE_IDENTIFIER)` callback scheme;
  do not add team, profile or signing material.
- Rename the internal generated Flutter project/package from
  `ntubtob_fictional_client` to `ntubtob_portal`, updating imports, metadata and
  reproduction instructions without removing the explicit fictional
  development composition.
- Add one narrowly scoped GitHub Actions workflow that runs only for relevant
  Flutter/workflow changes. Pin Flutter exactly to `3.47.0`, cache safely, and
  pin every third-party action by full commit SHA after verifying its upstream
  repository and documented inputs. Least-privilege permissions are mandatory.
- Hosted gate runs dependency resolution, format check, analyze, all Flutter
  tests and an Android development/fake debug build with explicit non-secret
  defines. The APK is an ephemeral CI artifact only if upload is needed for
  diagnosis; it must never be committed or presented as a release artifact.
- Integrate the Flutter gate into the existing final-gate semantics without
  weakening or duplicating the Python/security checks. If the existing
  classifier/final gate cannot safely express the new job, escalate to Main
  Work rather than silently making Flutter optional.

## Invariants

- No real API URL, LINE channel ID, token, Secret, keystore, provisioning
  profile, signing certificate or store credential enters source, workflow,
  cache key, artifact name or logs.
- Hosted build uses `APP_FLAVOR=development` and `CLIENT_MODE=fake`; it performs
  no external API or LINE login call. Dependency and action downloads are the
  only expected network access.
- No backend, OpenAPI, shared library, schema, production, staging, deployment,
  notification or cloud resource change.
- Generated build output, `.dart_tool`, Gradle cache, APK and machine-local
  files remain ignored and untracked.

## Writer boundary

Flutter Domain Work directs one existing Flutter Codex writer in an independent
worktree/branch. The implementation writer may modify only:

- `clients/flutter_app/**`
- `.github/workflows/flutter-tests.yml`
- the minimum existing final-gate/classifier workflow lines strictly required
  to make the Flutter job required for relevant changes
- `docs/coordination/reports/TASK-111-CODEX.md`

Flutter Domain Work may maintain this task status and the single
`docs/coordination/reviews/TASK-111-FLUTTER-WORK.md` on the shared integration
branch. It must not modify root HANDOFF/PROJECT_STATE/DECISIONS or application
backend/schema files. Workflow scope expansion or inability to pin an action is
a Main Work escalation.

## Verification

- Repository-wide search proves the old `com.example` application identity and
  old internal package imports are gone from active Flutter runner/source/tests.
- Android merged manifest/debug APK identity and label are correct; debug-only
  signing is explicit and no release signing fallback exists.
- iOS project/plist static review proves the approved bundle/display identity,
  derived callback scheme, target 15 and absence of signing material. Runtime
  iOS build remains deferred to macOS.
- Local `flutter pub get`, Dart format check, `flutter analyze`, all tests and
  fake Android debug build pass with the TASK-107 toolchain.
- Workflow syntax/static review, action-SHA provenance, permissions/cache/no-
  secret review, `git diff --check`, changed-file boundary and clean status.
- A Draft/final PR may be created early only to obtain the new hosted Flutter
  evidence. Final integration requires the Flutter job and existing required
  final gate to pass on the same accepted head.

## Not authorized / deferred

No real LINE Developer configuration, callback registration, API endpoint,
staging environment, Secret binding, migration, deployment, signing, APK upload
for distribution, TestFlight or store action is authorized. Those belong to the
subsequent isolated staging task.

## Execution checkpoint

1. Goal: establish stable app identity and repeatable hosted Flutter evidence.
2. Core files: Flutter runners/package metadata, one Flutter workflow, one
   report and only the minimal existing final-gate integration if required.
3. Invariants: no Secret/endpoint/signing, fake-only hosted build, existing
   security gates remain required.
4. Tests: identity/static scans, pub/format/analyze/tests/debug build, hosted
   Flutter job and existing final gate.
5. Blockers: workflow provenance or final-gate incompatibility returns to Main
   Work; real LINE/staging/iOS runtime are intentionally deferred.
