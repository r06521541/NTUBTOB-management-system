# TASK-169：Mobile Store Release Readiness

## Task metadata

- type: `delivery`
- delivery_group: `task-169-mobile-store-readiness`
- acceptance_level: `L2`（release／auth configuration boundary；repository-only）
- base: `d59663781c5602e1699f812d5a953cec12e0eeb4`
- branch: `codex/task-169-mobile-store-readiness`
- report_to: `main-work`
- owner_approved: 2026-08-31

## Product decisions

1. Android 近期 release target 是 Basic-only Google Play Closed Testing；Officer／Admin、push、deep link delivery與匿名 crash reporting仍是公開版前 gate，不阻塞第一個closed-testing candidate。
2. iOS 公開版採 Sign in with Apple，不以App Review例外作為release strategy；本task只交付repository contract與gap plan，不建立provider或production binding。
3. Main可在本task的獨立review `ACCEPT`、hosted CI全綠且PR無衝突後合併唯一PR至`main`；不得直接在`main`建立工作commit。

## Parallel writer claims

### Android release writer

- actor_id: `/root/task169_android_release_writer`
- role: `codex-writer`
- claim_id: `task-169-android-release-writer-20260831`
- lease_version: 1
- scope: Android API 36、release configuration／signing injection、AAB artifact inspection與CI regression
- owned_paths:
  - `clients/flutter_app/android/**`
  - `clients/flutter_app/pubspec.yaml`
  - `.github/workflows/flutter-tests.yml`
  - `tools/mobile_release*`
  - `tools/tests/test_mobile_release*`
  - `docs/coordination/reports/TASK-169-ANDROID.md`

### iOS／store compliance writer

- actor_id: `/root/task169_ios_compliance_writer`
- role: `codex-writer`
- claim_id: `task-169-ios-compliance-writer-20260831`
- lease_version: 1
- scope: iOS/TestFlight／Sign in with Apple repository contract、store privacy/data/account-deletion readiness與reviewable release matrix
- owned_paths:
  - `clients/flutter_app/ios/**`
  - `clients/flutter_app/lib/support_app_info.dart`
  - `clients/flutter_app/test/basic_app_test.dart`
  - `clients/flutter_app/test/support_app_info_test.dart`
  - `docs/releases/**`
  - `docs/README.md`
  - `docs/coordination/reports/TASK-169-IOS-COMPLIANCE.md`

Both writers may edit only their owned paths, must self-review／self-test, and may not commit before Main integration review. Each must acknowledge `received/executing`, proactively report blocker／heartbeat, and on completion send both a final response and a cross-session Main notification containing exact paths, tests, risks and task name.

## Required outcomes

1. Android release configuration explicitly targets API 36 and fails closed when package, flavor, version, signing injection or real-client HTTPS configuration is absent／mixed／debug-shaped.
2. No keystore, signing password, provider ID, account, Secret or production endpoint is committed. Release signing is external-only and testable with fictional metadata.
3. A deterministic repository tool/test verifies the release artifact contract needed for a future AAB candidate; CI exercises the minimum safe build／inspection path without store upload.
4. A deidentified mobile release matrix distinguishes Android Closed Testing, Android public release, iOS TestFlight and iOS public release; it includes privacy, Data Safety/App Privacy, account-deletion request path, store metadata, real-device, push/deep-link/crash and production backend gates.
5. iOS files provide a reviewable fail-closed Sign in with Apple／TestFlight configuration contract without claiming macOS/Xcode/signing evidence.

## Verification budget

- Writers: focused tests and format/static checks for owned paths.
- Main: complete Flutter test/analyze, Android release build／artifact inspection where supported, tooling tests, diff/scope review.
- One independent Release/Security targeted reviewer after integrated diff.
- One ready PR and change-selected hosted CI; merge only on immutable reviewed SHA, green required checks and no conflict.

## Stop conditions

- Need for real signing key/password, Play Console/App Store Connect login, developer-account purchase, raw provider/client data, Secret payload, cloud/production/runtime/deployment, store upload/publish or personal-device data.
- Cross-writer path overlap, unresolved package/bundle identity conflict, or inability to make release validation fail closed without introducing real configuration.
- A stopped lane records a bounded gap and returns to Main; it does not authorize a workaround or block safe independent work in the other lane.

## Acceptance and closeout

- Independent Release/Security review accepted immutable implementation SHA
  `ab07b665a3812d59459e04df6792432930e3bd43` with no findings.
- Hosted run `33331387388` passed every selected gate, including Flutter
  format/analyze/tests, Android API 36, the signed fictional contract-test AAB,
  strict artifact inspection and PostgreSQL 15/16.
- Delivery PR #219 merged conflict-free as
  `053888692ec1a5d6b7e2893c1f90c1d8320544d5`; final hosted run `33331935470`
  passed on its accepted head. TASK-169 is complete. No store upload, signing
  Secret, provider, cloud, production or deployment action was part of the
  merge.
