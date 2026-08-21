# TASK-107 Flutter Work review

status: accepted
reviewer: flutter_domain_work
reviewed_at: 2026-08-18T17:27:11+08:00
branch: codex/flutter-client-foundation
implementation_commit: 2fe59caabdcc7e30fb1e6102756db0ffef9b7b2a

## Review result

TASK-107 accepted。Flutter／Android toolchain 已以官方、user-scoped、可移除方式啟用；Android／iOS runners 與
Flutter metadata 已生成並逐檔審查，TASK-105 source/tests 保留。真實 format、analyze、13 tests 與 Android
development debug build 證據通過。Windows 無法驗證 iOS build/signing，仍須後續 macOS/Xcode/CocoaPods gate。

## Toolchain and external writes

- Flutter stable `3.47.0`、Dart `3.13.0`，framework `4cf2416426`；官方 archive SHA-256
  `9f96d393cdfad05bea0b4b42c603ffda027af11adadc8e4cf3ac87e49110c1ca` 已核對相符。
- Google Android command-line tools `22.0`、SDK platform/build-tools `36/36.0.0`、ADB `37.0.1`、NDK
  `28.2.13676358`；7/7 licenses accepted。
- Microsoft OpenJDK `17.0.20+8-LTS`。
- Task-scoped root 為 `C:\Users\USER\.codex\toolchains\task-107`；只使用 session-scoped PATH／環境設定，未改永久
  PATH。關閉 Flutter/Gradle/ADB 後可整體刪除此 task root；共享 AppData cache 不得廣泛刪除。

## Runner and source review

- Android/iOS identifiers 保持 template fictional `com.example...`；未加入正式 resource、team、profile、keystore、
  endpoint 或 credential。
- Android main manifest 無 INTERNET；只有 debug/profile manifests 保留 Flutter debug/hot reload 所需 INTERNET。
- Android release build type 已移除 template debug signing fallback，未設定 release signing；未執行 release build。
- iOS 保留 template automatic signing，但沒有 development team/profile；Windows 未執行 Xcode build/signing。
- TASK-105 `lib/` 與 tests 只有官方 formatter及 Flutter 3.47 真實 compile gate 所需的最小修正；功能語意未擴張。
- Generator 的無關 template widget test 已移除；`flutter_lints 6.0.0`、lockfile與 metadata 為 runner/analyzer 所需。

## Evidence reviewed

- `flutter pub get`：成功。
- `dart format --output=none --set-exit-if-changed .`：3 files、0 changes；Flutter Work 另以 Dart binary重跑通過。
- `flutter analyze`：`No issues found`。
- `flutter test`：13/13 passed。
- `flutter build apk --debug --dart-define=APP_FLAVOR=development`：成功；APK 僅在 ignored `build/`，未提交。
- `adb devices -l`：無 emulator／實機，故沒有裝置互動 smoke；這是目前唯一 Android runtime residual risk。
- Cumulative diff、writer boundary、tracked/ignored artifact、release signing、manifest permission、Secret/endpoint 與
  branch/origin/clean status 已逐項驗收。Flutter Work 的額外 Flutter CLI 重跑受當時 startup contention 阻塞，未取代
  實作者 thread 中已保存的成功 command evidence。

## Safety and residual risk

未提交 APK/AAB、build cache、`.dart_tool`、`local.properties`、Gradle cache、IDE files、keystore或 credential。
未連 production/API/auth/schema/shared model/真通知，未 release signing、upload、deploy、PR 或 main merge。後續若要
驗證 Android 裝置或 iOS，需另由 Main Work 配發具 emulator/實機或 macOS/Xcode 的工作包；本 task 不授權發布。
