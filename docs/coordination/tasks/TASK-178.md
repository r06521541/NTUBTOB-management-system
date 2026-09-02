# TASK-178：iOS TestFlight macOS Compile Gate

## Task metadata

- type: `delivery`
- delivery_group: `task-178-ios-testflight-compile-gate`
- acceptance_level: `L2`（release／auth configuration boundary；repository-only）
- base: `1c5348f923d23347071cc09b31408ff8703b8805`
- branch: `codex/task-178-ios-testflight-compile-gate`
- report_to: `main-work`
- owner_approved: 2026-09-02

## Product outcome

在不等待Apple Developer enrollment、不取得真實signing/provider資料，也不建立或上傳TestFlight candidate的前提下，
新增hosted macOS／Xcode compile gate，編譯`staging:real + Release`的iOS client與原生Apple authorization bridge。
此gate只消除repository source在macOS/Xcode無法編譯的風險；不得宣稱codesign、archive、TestFlight、真機或公開版ready。

## Writer claim

- actor_id: `/root`
- role: `codex-writer`
- claim_id: `task-178-ios-testflight-compile-gate-writer-20260902`
- lease_version: 1
- scope: iOS no-codesign contract-test vector、hosted macOS compile gate、focused regression與release evidence
- owned_paths:
  - `.github/workflows/flutter-tests.yml`
  - `tools/tests/test_ci_workflow_contract.py`
  - `clients/flutter_app/ios/validate_store_release_config.sh`
  - `clients/flutter_app/ios/tests/validate_store_release_config_test.sh`
  - `clients/flutter_app/ios/README.md`
  - `clients/flutter_app/ios/Runner.xcodeproj/project.pbxproj`
  - `clients/flutter_app/pubspec.yaml`
  - `clients/flutter_app/pubspec.lock`
  - `tools/tests/test_mobile_release.py`
  - `docs/releases/MOBILE_RELEASE_MATRIX.md`
  - `docs/coordination/tasks/TASK-178.md`
  - `docs/coordination/reports/TASK-178.md`
  - `docs/coordination/HANDOFF.yaml`
  - `docs/coordination/PROJECT_STATE.md`

## Required behavior

1. Contract-test只接受`staging:real + Release + testflight`、exact production-shaped bundle identity、explicit version/build、
   `CODE_SIGNING_ALLOWED=NO`及所有external signing/provider readiness為absent／false。
2. Contract-test不得接受production flavor、Apple runtime marker、provider-ready、signing-ready、team/profile/identity、
   entitlements binding或任何混合／未知設定；actual TestFlight/App Store candidate路徑保持原本fail-closed契約。
3. Hosted macOS job只編譯no-codesign iOS app並確認產物存在；不得upload artifact、登入App Store Connect、建立profile、
   讀取Secret或保留真實provider資料。
4. 現有`APPLE_SIGN_IN_REPOSITORY_STATUS=not_implemented`保持不變；本task不提前解鎖公開版。
5. Xcode project與Runner target的Debug／Release／Profile皆須明確使用iOS 15.0；不得依賴Flutter預設值，
   以符合現行LINE SDK的最低平台要求。
6. `flutter_line_sdk`須使用官方已將Swift package最低平台修正為iOS 15、且相容Flutter 3.47的版本；
   不得在hosted runner內修改pub cache或vendor未審查的套件副本。

## Independent reviewer claim

- actor_id: `/root/task178_release_security_review`
- role: `advisor/reviewer`
- claim_id: `task-178-ios-compile-release-security-reviewer-20260902`
- lease_version: 1
- write: `read-only`
- report_to: `/root`
- scope: immutable TASK-178 SHA的compile-only isolation、actual candidate non-regression、workflow no-secret/no-artifact boundary

Reviewer須先回`received/executing`；超過10分鐘主動heartbeat；完成後主動回完整SHA、verdict、tests、findings、
remaining limits與external mutations。不得修改working tree、commit、push、PR或任何外部狀態。

## Verification budget

- iOS shell validator完整regression。
- Flutter Apple/auth focused tests與format/analyze。
- hosted macOS/Xcode no-codesign compile gate。
- 一位獨立Release/Security targeted reviewer；一個ready PR與change-selected hosted CI。

## Stop conditions

- 需要真實Apple帳號、Team ID、App ID、certificate/profile、private key、provider/client value、Secret、macOS登入、
  App Store Connect、TestFlight upload、真機個資、cloud/runtime/deployment或production資料。
- 無法在不放寬actual candidate fail-closed path的情況下建立compile-only向量。
