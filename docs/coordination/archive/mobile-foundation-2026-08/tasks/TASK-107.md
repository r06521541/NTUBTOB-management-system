# TASK-107：Flutter toolchain enablement and runner verification

task_type: `work_package`
delivery_group: `flutter-client-foundation`
requires_independent_pr: `false`
狀態：`completed`
Owner／Main Work 配發日：2026-08-18
base：`codex/flutter-client-foundation` @ `e7891f6c01ec33ae200e936540d3512edf13e19f`

## 目標

以官方來源、user-scoped、可移除且版本可重現的方式啟用 Windows Flutter／Android toolchain，為 TASK-105
fictional source foundation 生成並審查 Android／iOS runners 與 Flutter metadata，取得真實 analyze、test 與可行的
Android debug build 證據。本 task 不擴張產品功能或建立跨端契約。

## Toolchain inventory 與安裝授權

實作前唯讀記錄 Flutter、Dart、Java、Android SDK／command-line tools／build tools／platform tools、環境變數及既有
安裝位置。Owner 已明確批准本 task 必要的下載與安裝，限以下邊界：

- 只從 Flutter、Google Android 或相容 JDK 的官方來源取得 current stable／相容版本。
- 優先安裝在 user-scoped、可移除目錄；記錄精確版本、來源 URL／channel、安裝位置、session PATH 方式與清理方法。
- 不修改 repository Makefile，不把 machine-specific absolute path 寫入 app source，不讀寫 Secret。
- 需要 admin elevation、帳號登入、license 互動或無法自動完成的真人步驟時，先完成其餘工作再依工具流程請求批准。

## 實作範圍

### Doctor 與 Android prerequisites

- 使 `flutter doctor -v` 可執行並保存實際結果摘要。
- 補齊相容 Android command-line tools、SDK platform、build tools 與 platform tools；可接受 Android SDK licenses，
  但不得登入帳號、設定 signing key 或 release credential。
- Windows 無法驗證 iOS build/signing；明確記錄後續 macOS、Xcode、CocoaPods 與 signing gate，不假稱通過。

### Runner generation 與逐檔審查

- 在 `clients/flutter_app/` 依既有 README gate 生成 Android／iOS runners與必要 Flutter metadata。
- 生成前後核對 TASK-105 source/tests，禁止覆寫、刪除或靜默改寫既有 fictional behavior。
- 逐檔審查 application／bundle identifiers、debug/release signing defaults、endpoint／credential、Android network
  permission、generated dependency 與無關產物；只接受本 task 必要的 runner／metadata diff。
- 不加入正式 resource、hostname、token、keystore、provisioning profile 或 production reference。

### 真實驗證與最小修正

在 `clients/flutter_app/` 執行：

```sh
flutter pub get
dart format --output=none --set-exit-if-changed .
flutter analyze
flutter test
```

修正上述命令揭露的 TASK-105 compile／runtime／widget test 問題，但不得藉機擴張產品功能。條件允許時執行 Android
debug build 或不需真人操作的 smoke；不得 release build、sign、upload 或發布 APK。Emulator／硬體加速／實機若需
Owner 操作，先交回已完成的非互動證據與精確 blocker。

## Writer boundary

主要 Flutter Codex 只可修改：

- `clients/flutter_app/**`
- `docs/coordination/reports/TASK-107-CODEX.md`

Flutter Domain Work 維護本 task 與唯一 `docs/coordination/reviews/TASK-107-FLUTTER-WORK.md`。不得修改 global
DEC、root `HANDOFF.yaml`、PROJECT_STATE、root Makefile、shared_lib、Web／LINE／Functions 或 schema 檔案。

Toolchain 安裝可寫入 task 專用 user-scoped 外部目錄，但不得提交 binaries、SDK cache、credential 或 machine-local
absolute path。實作者交回時須列出所有 repository 外寫入與清理方法。

## 明確禁止

- 不建 mobile/backend API，不串 LINE auth、DB/schema、真 push、Discord 或通知。
- 不連 production，不部署，不建立或使用 signing credential。
- 不產出供發布的 APK／AAB，不操作 TestFlight 或商店。
- 不修改跨端 authentication、authorization、API、shared model 或通知語意；需求立即升級 Main Work。

## 驗收條件

- Inventory 含官方來源、精確版本、安裝位置、PATH 方式、清理方法與 `flutter doctor -v` 結果。
- TASK-105 source/tests 保持存在；runner／metadata cumulative diff 已逐檔審查且無 Secret、endpoint 或 production reference。
- `flutter pub get`、format check、`flutter analyze`、`flutter test` 有實際 command/result 證據。
- Android debug build/smoke 能自動完成則執行；否則回報精確缺項與已完成部分。
- iOS 明確 deferred 至 macOS/Xcode gate，不宣稱 Windows 已驗證。
- 執行 no-secrets／no-endpoints scan、`git diff --check`、branch／remote SHA 與 clean status 檢查。

## 最小交回格式

- Branch、base、完整 HEAD、dirty state、changed files。
- Toolchain 版本／來源／位置／PATH／清理與 repository 外副作用。
- Runner review、實際驗證命令與結果、未驗證平台風險。
- 無 production／Secret／signing／deployment／release 副作用聲明。
