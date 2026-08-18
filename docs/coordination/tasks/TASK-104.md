# TASK-104：Flutter client foundation planning

task_type: `planning`
delivery_group: `flutter-client-foundation`
requires_independent_pr: `false`
狀態：`completed`
Owner 確認日：2026-08-18

## 目標

將 Owner 與 Flutter planning session 收斂的第一階段產品、session、API、權限、通知、staging 與安全邊界固化為可驗收規格，並提出後續 implementation work packages。完整規格位於 [`docs/planning/FLUTTER_CLIENT_PLAN.md`](../../planning/FLUTTER_CLIENT_PLAN.md)。

本 task 不一次實作全部產品願望，也不建立正式 implementation TASK 編號。

## 範圍

- 建立 Flutter 第一階段產品與 capability matrix。
- 固化 LINE native Login、token／session、Person／AuthIdentity 與 mobile API 方向。
- 固化會員、Officer、Admin 的功能與通知邊界。
- 定義 fictional demo、offline read-only、retry 與 staging TestFlight／APK 方向。
- 盤點後續 A～E 候選 work packages：fictional foundation、schema-neutral attendance service、mobile auth/API contract、Flutter API integration、staging/release。
- 明列現有 DEC 的引用、衝突與 deferred questions。

## 非範圍與未授權事項

- 不實作 Flutter App、不安裝 Flutter、不建立 API、不修改 schema／migration／model。
- 不連 production DB，不讀取或操作 Secret，不修改 IAM／Scheduler／cloud resource。
- 不發送真實 LINE／Discord／push 通知。
- 不部署 production 或 staging，不建立 TestFlight／商店發布物，不發布 APK。
- 不因 fictional demo、規劃文件或 future capability 宣稱 production Officer／Admin resolver 已啟用。
- DEC-078 管 production／外部操作批准，DEC-082 管 production admin allowlist，DEC-089 只規範 bounded Game routes／session-only lineup；本 task 不宣稱 production Officer／Admin resolver 已啟用，任何語意衝突交回 Main Work。

## Toolchain inventory（唯讀盤點）

### 已知

- Repository 目前有 Python／Flask Web Portal 與共用 PostgreSQL／identity／attendance domain。
- Flutter client source 尚需在後續 A package 盤點；本 task 不安裝 SDK 或改動 toolchain。
- Windows／Codex 操作遵循 `docs/development/AGENT_ENVIRONMENT.md`。

### 待盤點

- Flutter SDK stable channel、Dart 版本與可用 Android／iOS toolchain。
- Android SDK／emulator、Xcode／iOS simulator 與真機簽署條件。
- LINE native SDK／plugin 的版本、平台支援與 redirect／universal link 條件。
- staging API、push provider、crash reporting 與 TestFlight／Internal App Sharing 的 Owner 資源。

## 後續候選 work packages

正式 TASK 編號由總控 Work 後續配置：

- A：Flutter fictional foundation。
- B：schema-neutral attendance reply application service（Web + LINE）。
- C：mobile auth／API contract。
- D：Flutter API integration。
- E：staging／release。

候選 packages 不代表已授權實作、schema、部署、Secret、正式通知或商店發布。

## 驗收條件

- `FLUTTER_CLIENT_PLAN.md` 以主題整併決策，沒有使用對話中的 DEC-001～073 作全域編號。
- 本 task 具備 planning metadata、範圍、非範圍、toolchain inventory、候選 slicing 與 deferred questions。
- `DECISIONS.md` 只新增跨 task、長期有效且不與 DEC-079／080／082／084／085／089／090 衝突的濃縮決策。
- `PROJECT_STATE.md` 保持現在式且不超過 200 行；`HANDOFF.yaml` 指向 TASK-104 planning。
- 通過文件快速檢查、`git diff --check` 與工作區狀態檢查。
