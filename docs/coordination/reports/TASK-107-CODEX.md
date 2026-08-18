# TASK-107 Codex report

## Result

在 `codex/task-107-flutter-toolchain`、base `3df9bb3aa6b9f13441b3b33636dd59cd6ed277d8` 完成 Windows Flutter／Android toolchain enablement。依既有 generation gate 產生 Android/iOS runners 與 Flutter metadata；TASK-105 source/tests 保持存在。真實執行 format、analyze、13 項 tests 與 Android development debug build。iOS build/signing 留待 macOS/Xcode/CocoaPods gate。

## Toolchain inventory and external writes

- 初始盤點：無 `flutter`、`dart`、`adb`、Android SDK、`ANDROID_HOME`、`ANDROID_SDK_ROOT`、`JAVA_HOME`；僅系統 Microsoft OpenJDK `11.0.16.1`。
- Flutter：官方 release manifest `https://storage.googleapis.com/flutter_infra_release/releases/releases_windows.json`；stable `3.47.0`、Dart `3.13.0`、framework `4cf2416426`。下載 `flutter_windows_3.47.0-stable.zip`，官方 SHA-256 `9f96d393cdfad05bea0b4b42c603ffda027af11adadc8e4cf3ac87e49110c1ca` 驗證相符。
- Android command-line tools：Google 官方 Android Studio 頁解析 artifact `commandlinetools-win-15859902_latest.zip`，來源 `https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip`，CLI `22.0`。
- Android SDK：platform `android-36`、build-tools `36.0.0`、platform-tools/ADB `37.0.1`、NDK `28.2.13676358`；7/7 SDK licenses accepted。NDK 由 debug build 依 Flutter template 自動安裝。
- JDK：Microsoft 官方 `https://aka.ms/download-jdk/microsoft-jdk-17-windows-x64.zip`，OpenJDK `17.0.20+8-LTS`。
- 主要 task-scoped root：`C:\Users\USER\.codex\toolchains\task-107`，包含 Flutter、Android SDK、JDK、downloads、Gradle cache、Android user home。session PATH 僅加入 Flutter bin 與 platform-tools；未修改永久 PATH／環境變數。
- Flutter 也觀察到 user-scoped state/cache：`C:\Users\USER\AppData\Roaming\.flutter_settings`、`.flutter_tool_state`、`.dart-tool` 與 `C:\Users\USER\AppData\Local\Pub`。這些位置可能含既存共享資料，不應整體刪除；若清理，先比對 task 前備份／ownership，只移除本 task 新增項目。
- 安全清理：關閉 Flutter/Gradle/ADB process 後，可整體刪除 task-scoped root；repository build/cache 由 `flutter clean` 清理。不得廣泛刪除共享 AppData cache。

## Doctor and runner review

- 最終 `flutter doctor -v`：Flutter、Windows、Android toolchain、Chrome、Visual Studio、devices、network resources 通過；唯一 warning 是 Flutter/Dart 未加入永久 PATH，為刻意的 session-scoped 設計。
- `flutter create --platforms=android,ios --project-name ntubtob_fictional_client .` 成功。生成後 tracked `lib/`、既有 `test/foundation_test.dart`、`pubspec.yaml` 未被 generator 靜默覆寫；後續只因真實 formatter/compile gate 做必要修正。
- Android/iOS identifiers 保持 template fictional `com.example.ntubtob_fictional_client`／`com.example.ntubtobFictionalClient`，無正式 resource、team、profile、keystore、endpoint 或 credential。
- Android main manifest 無 INTERNET；debug/profile manifest 僅保留 Flutter tool hot reload/debug 所需 INTERNET。Android release build type 已移除 template 的 debug signing fallback，保持 unsigned；未執行 release build。
- iOS 為 template automatic signing 設定但無 development team/profile；Windows 未執行 Xcode build 或 signing。
- 刪除 generator 的無關 `test/widget_test.dart`；保留 TASK-105 tests。新增 generator 對應 `flutter_lints 6.0.0` dev dependency，並移除 Flutter 3.47 不接受的 const `Semantics` 呼叫。

## Verification evidence

- `flutter pub get`：成功；lockfile generated。
- `dart format --output=none --set-exit-if-changed .`：成功，3 files、0 changes（先以 `dart format .` 收斂既有兩檔格式）。
- `flutter analyze`：成功，`No issues found`。
- `flutter test`：成功，13/13 tests passed。
- `flutter build apk --debug --dart-define=APP_FLAVOR=development`：成功，ignored debug APK `build/app/outputs/flutter-apk/app-debug.apk`，150,379,350 bytes；未提交 APK。
- `adb devices -l`：零 Android device/emulator，因此未執行安裝／互動 runtime smoke；其餘非互動工作已完成。
- 最終執行 no-secret/no-endpoint/no-production-reference scan、cumulative `git diff --check`、branch/remote SHA 與 clean status 檢查。

## Safety and residual risk

未讀寫 Secret、未加入 endpoint/production reference、未設定 release signing、未建立 release APK/AAB、未上傳／發布／部署、未連 API/auth/schema/shared model/真通知。Windows 無法驗證 iOS；後續需 macOS、相容 Xcode/CocoaPods 與由 Owner 另行批准的 signing boundary。
