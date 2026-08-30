# TASK-169 iOS／Store Compliance Codex report

- actor: `/root/task169_ios_compliance_writer`
- claim: `task-169-ios-compliance-writer-20260831` / lease 1
- authority checkpoint: `aec506662eb15a7efd8f1830216d2f243b819ffd`
- branch: `codex/task-169-mobile-store-readiness`
- state: ready for Main integration review; uncommitted by task instruction

## Delivered

1. Xcode 的既有 auth validation phase 先執行 `validate_store_release_config.sh`：只接受
   非distribution的`development/fake/Debug|Profile`、`staging/real/Debug|Profile`、
   `staging/real/Release/testflight` 與
   `production/real/Release/app-store` 明確向量；缺值、混用、release非Release、debug/test-shaped bundle、未明確
   version/build或外部signing metadata皆exit 2。
2. `StoreReleaseContract.xcconfig` 由repository控制並最後include；目前固定
   `APPLE_SIGN_IN_REPOSITORY_STATUS=not_implemented`；validator直接讀該檔並要求resolved Xcode值一致，private／
   command-line build setting均無法覆寫，因此production/App Store build fail closed。未來即使經review改為`ready`，仍須
   runtime marker、external provider readiness與受review的entitlement才可通過。
3. private store config與Apple entitlement只提供空白／未綁定example；真實team、profile、identity、provider、
   certificate、password與Secret均未加入repository。
4. 支援頁明示「帳號刪除申請」、安全申請內容與「登出不等於刪除」；沒有假稱已提供backend deletion或store-complete
   流程。
5. `MOBILE_RELEASE_MATRIX.md`分開Android Closed Testing、Android public、iOS TestFlight與iOS public，涵蓋
   privacy、Play Data Safety／Apple App Privacy、帳號刪除、metadata、signing、真機、push、deep link、匿名crash、
   production backend、review／rollback；所有外部證據未知時一律`BLOCKED`。

## Verification

- `C:\Program Files\Git\bin\bash.exe clients/flutter_app/ios/tests/validate_store_release_config_test.sh`
  - PASS：14組fictional contract vectors，含fake/staging non-distribution Debug／Profile、Debug不得claim TestFlight、
    TestFlight success、missing/mixed/signing/bundle failures、目前production blocked、repository-ready但runtime
    missing blocked、private/CLI readiness override blocked、future complete fictional vector。
- `Invoke-FlutterToolchain.ps1 flutter test test/integration_test.dart test/support_app_info_test.dart`
  - PASS：61 tests；包含既有iOS Google/private scheme build-phase regression與support UX。
- `Invoke-FlutterToolchain.ps1 flutter analyze lib/support_app_info.dart test/support_app_info_test.dart`
  - PASS：no issues。
- `Invoke-FlutterToolchain.ps1 dart format --output=none --set-exit-if-changed ...`
  - PASS：2 files，0 changed。
- `bash -n clients/flutter_app/ios/validate_store_release_config.sh clients/flutter_app/ios/tests/validate_store_release_config_test.sh`
  - PASS。
- PowerShell XML parse：`Runner/Runner.entitlements.example`與既有`Runner/Info.plist` PASS。
- `git diff --check`
  - PASS；只有Windows checkout的LF→CRLF warning，沒有whitespace error。

Test-first red/green紀錄：support文字增加後首次focused test因Build tile移出viewport而失敗，測試補明確scroll後通過；
內嵌`.debug.` bundle regression首次證實validator未拒絕，改為segment-aware pattern；self-review另發現staging Debug
既有Debug／Profile開發路徑被誤阻，先補red regression後限縮為無distribution claim才可執行；最後以完整fictional
Apple vector證實resolved build setting原可覆寫repository marker，改為直接讀repository source並要求一致後，最終14組
contract全通過。Git Bash及Flutter
第一次在sandbox內分別因Win32 signal pipe／toolchain lock permission失敗，依環境指引在核准的sandbox外重跑成功；沒有
殘留產品失敗。

## Not verified／remaining gates

- 本機是Windows，未執行macOS/Xcode archive、CocoaPods、codesign/profile inspection、TestFlight upload/install、
  iOS真機、App Store Connect、App Review或provider操作；不得將本report視為上述證據。
- Sign in with Apple client/backend/linking/recovery尚未實作；actual entitlement未建立或綁定，Apple provider/App ID未設定。
- Play Data Safety／Apple App Privacy表單、store metadata/URLs/screenshots、可由reviewer啟動的帳號刪除request lifecycle、
  push/deep-link delivery、匿名crash receipt與production backend仍須未來Owner-gated work package。
- 沒有使用真實帳號、provider/client ID、signing material、Secret、network/store/cloud/production/deploy或真實資料。

## Exact changed paths

- `clients/flutter_app/ios/.gitignore`
- `clients/flutter_app/ios/Flutter/Debug.xcconfig`
- `clients/flutter_app/ios/Flutter/Release.xcconfig`
- `clients/flutter_app/ios/Flutter/StoreReleaseConfig.xcconfig.example`
- `clients/flutter_app/ios/Flutter/StoreReleaseContract.xcconfig`
- `clients/flutter_app/ios/README.md`
- `clients/flutter_app/ios/Runner/Runner.entitlements.example`
- `clients/flutter_app/ios/Runner.xcodeproj/project.pbxproj`
- `clients/flutter_app/ios/tests/validate_store_release_config_test.sh`
- `clients/flutter_app/ios/validate_store_release_config.sh`
- `clients/flutter_app/lib/support_app_info.dart`
- `clients/flutter_app/test/support_app_info_test.dart`
- `docs/README.md`
- `docs/releases/MOBILE_RELEASE_MATRIX.md`
- `docs/coordination/reports/TASK-169-IOS-COMPLIANCE.md`
