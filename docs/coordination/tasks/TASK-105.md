# TASK-105：Flutter fictional foundation

task_type: `work_package`
delivery_group: `flutter-client-foundation`
requires_independent_pr: `false`
狀態：`ready_for_codex`
Owner／Main Work 配發日：2026-08-18

## 目標

在 `clients/flutter_app/` 建立 Flutter-only fictional foundation，讓 Android／iOS 第一階段產品可先以 deterministic fake data 驗收資訊架構、角色導覽、theme、狀態頁與 offline read-only 行為。此 work package 不建立或推定任何 mobile/backend contract。

規劃依據：[`docs/planning/FLUTTER_CLIENT_PLAN.md`](../../planning/FLUTTER_CLIENT_PLAN.md)。

## Toolchain inventory

2026-08-18 於 Windows Codex worktree 唯讀確認：

- `flutter`：不可用。
- `dart`：不可用。
- `adb`：不可用。
- Android SDK：`ANDROID_HOME`／`ANDROID_SDK_ROOT` 均未設定。
- Java：Microsoft OpenJDK 11 可用，但 `JAVA_HOME` 未設定。
- Repository：尚無 `pubspec.yaml`、Flutter `lib/`、Android 或 iOS client scaffold。

不得為本 task 下載或安裝 Flutter／Dart／Android SDK。實作者應完成可審查的 repository scaffold 與離線測試設計，將無法執行的 Flutter command 原樣回報；不得宣稱 analyze／test 通過。

## 實作範圍

### Project 與 flavor boundary

- 在 `clients/flutter_app/` 建立最小 Flutter app scaffold、Flutter-local README 與 tests。
- 建立 development／staging／production 的 compile-time flavor model；設定只能是環境名稱、display label 或 fictional feature toggle。
- 不放 API endpoint、hostname、credential、token、channel ID、bundle secret 或 production resource reference。
- 若缺少 Flutter SDK 無法安全產生 Android／iOS runner boilerplate，不手寫或假造 generated platform files；以明確 README 指令與 deferred inventory 記錄後續 `flutter create`／platform generation gate。

### Navigation、theme 與 UI states

- 手機直向、繁體中文、明亮／深色 theme shell。
- 建立 fictional Basic／Officer／Admin capability UI；Admin 包含 Officer，Officer 包含 Basic。
- 導覽至少涵蓋首頁、賽程、通知、帳號；Officer 增加單場出席摘要／通知 shell；Admin 增加系統公告 shell。
- UI visibility 只作 fictional preview，不宣稱 authorization；capability policy 需集中且 fail closed。
- 建立 loading、empty、error、offline states；所有文字使用友善繁體中文。

### Fake repository、fixtures 與 offline read model

- 建立抽象 repository boundary 與 deterministic fake implementation，不發 HTTP／socket／platform push 請求。
- Fixtures 至少涵蓋帳號、賽程、已回覆名單、通知、Officer 出席摘要與 Admin 公告。
- offline model 只能讀最近一次成功同步 snapshot，顯示固定／可注入的 `lastSyncedAt`；不得提供離線 mutation 成功假象。
- Fake push 只保存 deterministic in-memory notification events，不能呼叫 FCM、APNs、LINE、Discord 或其他 provider。

## Writer boundary

主要 Codex 只可修改：

- `clients/flutter_app/**`
- `docs/coordination/reports/TASK-105-CODEX.md`

如需修改本 task 文件，先交回 Flutter Domain Work。不得修改 root global DEC、HANDOFF、PROJECT_STATE、shared_lib、`apps/web_portal/`、functions、LINE／Discord caller 或 TASK-106 預定檔案。

## 明確禁止

- 不建 mobile/backend API，不串 LINE native auth、token、PKCE 或 session。
- 不連 Web Portal、LINE webhook、shared_lib、schema、DB 或任何外部網路。
- 不實作真 push、Discord、LINE Messaging API 或 notification delivery receipt。
- 不放 endpoint、credential、Secret 或真實個資。
- 不部署 staging／production，不建立 APK、TestFlight 或商店發布物。
- 不修改跨端 API、authentication、authorization、schema、shared model 或通知語意；發現需求即停止並升級 Main Work。

## 驗收條件

- Flutter scaffold 與 flavor boundary 可由 README 清楚重現，且沒有 Secret／endpoint。
- Deterministic fixtures 與 fake repository 不依賴網路、系統時間或 production state。
- Basic／Officer／Admin capability inheritance 與導覽 visibility 有測試。
- light／dark theme、loading／empty／error／offline states 有 widget 或 unit tests。
- offline read-only snapshot 與最後同步時間有測試，不提供 mutation success path。
- 執行 no-secrets／no-endpoints／no-network scan、`git diff --check`、`git status --short`。
- Flutter SDK 可用時執行 `flutter analyze`、`flutter test`；不可用時回報 exact inventory 與未驗證風險。

## 最小交回格式

- Branch、完整 HEAD、dirty state、changed files。
- 完成／未完成範圍與 toolchain inventory。
- 實際驗證命令、結果與未執行原因。
- 外部副作用聲明與下一工作包建議。

