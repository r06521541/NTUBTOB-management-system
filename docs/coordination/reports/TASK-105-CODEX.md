# TASK-105 Codex report

## Scope

建立 `clients/flutter_app/` 的 Flutter-local fictional foundation：最小 `pubspec.yaml`、main entry point、flavor labels、集中 capability policy、基本導覽 shell、loading/empty/error/offline state enum、deterministic fake repository 與 offline read-only snapshot model，以及 unit test 設計。未建立 Android/iOS generated runner。

## Boundary and safety

development/staging/production 僅是環境顯示名稱；程式未包含 endpoint、hostname、credential、token、Secret、backend/mobile API、LINE/Discord、DB、真 push 或外部網路。Admin/Officer visibility 是 fictional preview，policy fail closed，不能代表 server authorization。

## Verification

- `flutter --version`、`dart --version`、`adb version`：不可用；`java -version` 顯示 Microsoft OpenJDK 11。
- `flutter analyze`、`flutter test`：未執行，因 Flutter/Dart SDK 不存在。
- 已完成 repository 內 no-secrets/no-endpoints/no-network 靜態掃描、`git diff --check` 與 `git status --short`。

## Handoff

SDK 可用後，執行 README 的 generation gate、`flutter pub get`、`flutter analyze`、`flutter test`，再補齊正式 widget coverage 與平台 runner smoke test。未產生任何外部副作用；下一工作包可在此 local boundary 上另行處理跨端契約。
