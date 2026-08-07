# TASK-070 Work review

## 結論

狀態：`accepted`

驗收 commit：`dfae960931b3cf2b03a9554e8815d8af7e25a2b8`

Phase C 的 migration、transactional repository、default-off runtime gate、LINE principal/session、pending review、
Person attendance bridge 與跨服務 fallback 大致完成；本機 PostgreSQL 16 與應用測試亦可重現通過。但目前仍有直接違反
TASK-070 已確認產品規則的 Web Portal 缺口，因此尚不能接受。

## Blocking findings

### 1. 一般賽事頁仍列舉尚未回覆姓名

TASK-070 第 101 行明定一般頁面只能顯示尚未回覆人數，不得列舉姓名；但 `game_roster()` 仍建立
`players_not_reply_yet`，而 `templates/game_roster.html` 仍逐一輸出這些姓名。請移除一般使用者可見的姓名列舉，並新增
route/template 測試證明 team player、guest player 與一般 active Person 均看不到未回覆姓名。若保留統計，只能顯示人數。

### 2. display/formal name 切換尚未接到 Web Portal

Repository 的 `attendance_summary(..., use_display_name=False)` 已有底層參數，但共用 analyzer 永遠使用預設值，Web Portal
route/template 也沒有安全的切換控制。TASK-070 第 41、106、139、176 行要求 active Person 可在賽事頁切換 display/formal
name，且 formal name 缺少時 fallback display name。請完成 allowlisted query/form state、傳遞到 analyzer/repository、UI 與離線測試；
不得把任意字串或姓名偏好存入 authentication session principal。

### 3. 已配對 identity 缺少 remap 管理 UI

`identity_admin_action()` 與 repository 雖支援 `remap`，但 `identity_admin.html` 對已配對 identity 只提供 unlink 與 status
動作，沒有目標 Member 選擇或 remap submit，因此管理者無法從產品介面執行已核准的 remap 流程。請補上明確確認、原因、
CSRF、目標 Member 選擇與 route/template 測試；仍須禁止 remap 當前登入 identity，且不得暗中恢復 revoked qualification、
Person status 或 identity security status。

## 已確認事項

- `PORTAL_DATA_PHASE_C_ENABLED` 僅在精確值 `true` 時啟用；未設定時維持 legacy path。
- 管理 mutation 仍同時受既有 Member allowlist、active/linked admin、CSRF 與 maintenance gate 約束。
- migration 為 0003 到 0004 的單一 head，review tables 啟用 RLS 且零 policy；無法解析 attendance Person 時 transaction abort。
- LINE callback session 僅保存穩定 ID，受保護 request 會重新解析 principal。
- 本輪未連 production DB、未執行 production migration、未部署、未發送 LINE/Discord、未變更 Secret/IAM/Scheduler。
- Codex report 所稱「不加入 dual-write」文字容易誤解；實際核可、unlink、remap 等操作有同步維護 legacy `line_users`
  與 Phase C identity。建議修正 report，明確表達「未啟用 production dual-write rollout」，避免與實作相反。

## Work 實際驗證

- 本機 PostgreSQL fixture：`setup_portal_data_legacy` → stamp 0001 → upgrade head：通過。
- `python -m unittest discover -s tests/portal_data`：141 passed。
- `python -m unittest discover -s apps/web_portal/tests -v`：115 passed、2 skipped（Windows 無 `make` / `sh`）。
- 其餘 Codex 報告所列套件曾平行啟動；因 Work 第一輪誤寫 `tests/tools` 而提早失去整批輸出，不能把該輪視為完整獨立證據。
  Codex 修正後應重新執行受影響 Web Portal、portal-data、webhook、notify 與 `tools/tests`，再更新 report。

首次 portal-data 重跑曾因新啟動的本機容器尚未建立 `ntubtob` schema 而失敗；依 runbook 初始化 fixture 後 141/141 通過，
判定為驗收環境前置未完成，不是產品 finding。

## 修正後驗收要求

- 補齊上述三項 UI/產品行為與離線測試。
- 更新 Codex report 的 dual-write 說明與實際重跑證據。
- 執行 Phase C artifact verifier、受影響完整測試、compile/import check、formatter check、`git diff --check` 與
  `git status --short`。
- 不得進行 production migration/data、deployment、真實通知、Secret/IAM/Scheduler 或 production flag enablement。

## 修正版複驗

修正 commit：`1ae131a0177fc17f70e4acaa5492e37edb1e2f2e`

上一輪三項 blocking findings 均已解除：一般賽事頁只顯示未回覆人數；formal/display name 由固定 allowlist query
切換且不寫入 authentication session；非目前登入的已連結 identity 提供具 CSRF、原因、目標 Member 與明確確認的
remap 入口。Dual-write 說明亦已釐清為本機 transaction projection，而非 production rollout。

Work 複驗結果：

- Local PostgreSQL 16 portal-data：143 passed。
- Web Portal：120 passed、2 platform skips。
- LINE webhook：19 passed。
- Notify cron：9 passed。
- Tools：41 passed。
- Phase C migration artifact verifier：passed。
- Phase C evidence artifact verifier：passed。
- compileall：passed。
- `git diff --check`：修正本 review 原有 EOF whitespace 後 passed。

非阻塞觀察：remap 表單目前以 `person_id` 判斷顯示，因此 disabled／blocked 且仍保留 Person 的 identity 也可能看到入口；
repository 會拒絕非 `linked` 狀態，不構成授權或資料風險。後續可將 UI 條件收斂為 `identity_status == 'linked'`。

最終驗收：`accepted`。本結論不授權 production migration、feature enablement 或 deployment。
