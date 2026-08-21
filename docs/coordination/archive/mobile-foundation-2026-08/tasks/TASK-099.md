# TASK-099：Schema-neutral Portal management closure and repeatable local UI demo

task_type: delivery
delivery_group: phase-d-portal-management-closure
requires_independent_pr: true
status: ready_for_codex
owner: work
codex: codex

## 使用者價值

把 TASK-098 實際 localhost 驗收發現的缺口收斂成下一次部署前的完整操作閉環：allowlist Admin 可在人員介面
指派或解除 Officer；Basic／Officer／Admin 看到正確的賽程與管理導覽；所有既有 active Portal 使用者可讀精簡
Attendance；Windows 不再因 POSIX-only 日期格式 500；並把 deterministic fictional local UI demo 正式化為 Owner
可反覆使用、可 reset、不可誤碰 cloud-derived preview 的日常 QA 模式。

## 固定邊界

- Database revision 固定 `0004_phase_c_identity_lifecycle`；不得新增或修改 schema、migration、model 欄位、受控
  export SQL 或 production data contract。
- Production Admin authority 仍只由 `WEB_PORTAL_ADMIN_MEMBER_IDS` runtime allowlist 決定；Person `admin` 不取代
  allowlist。UI 只允許 `basic ↔ officer`，不得建立／解除 Admin。
- Officer 只取得既有 bounded Game command center 能力；不得因此存取 Person、pending identity、qualification、
  role assignment、notification 或 audit management。
- Game 資訊、Roster 與 Officer 的 Attendance 檢視維持唯讀；既有 Member 自己的出席回覆行為不變。
- Production-shaped cloud-derived local preview 維持 database read-only、POST fail closed；fictional demo 與
  cloud-derived preview 是兩條互斥 workflow，不得把資料混在同一 local database state。
- 不部署、不操作 production／Secret／IAM／Scheduler／cloud resource、不執行正式資料異動、不發送通知。
- 原 dirty 現場的 `tools/portal_preview_owner_bundle.py` 不在本 task；production read-only export 另需 Owner 精確批准。

## 1. Repeatable fictional local UI demo

以原工作現場 `tools/seed_portal_ui_demo.py` 為需求／baseline，Codex 必須重新驗收後才納入 task branch，不得直接
視為已完成。工具需提供 deterministic seed/reset workflow，至少包含：

- Demo Admin、Officer、Basic；每個需符合其正式頁面所需的 confirmed identity／Person／Member 關係。
- 約 15 位可試排候選、Member coach、guest player，以及出席／晚到／早退／不出席／未回覆分類。
- 未來、近期、過去與取消 Game；資料只能使用固定 fictional 名稱與保留 ID range。
- 只接受 loopback、exact local demo database、revision `0004`，並在 engine／mutation 前 fail closed。
- 只接受 repository-owned setup＋0004 fixture，或可精確辨識的 TASK-099 demo fixture；cloud-derived、任意 non-empty
  或 mixed state 必須拒絕且不修改。
- Seed／reset／cleanup 使用 transaction；重跑 deterministic、idempotent，late failure rollback。
- 不接受 DSN fallback、不連 Supabase、不讀 Secret、不發 HTTP、不建立 schema；輸出不得含 row data。
- Runbook 明確區分 `fictional demo` 與 `cloud-derived preview`，並提供 Windows bundled Python 指令及精確 cleanup。

若既有 importer／local DB gate 無法安全支援另一個 exact demo database name，優先讓 demo 僅接受 repository fixture
並以明確 confirmation 執行；不得為方便而放寬 production-shaped importer。

## 2. Admin 指派 Officer

- 在 `/manage/people/<person_id>` 提供 allowlist Admin 專用 `basic → officer` 與 `officer → basic` POST。
- 重用既有 transactional `change_access()`、audit、request ID、reason、row lock 與 authorization；不得建立第二套
  role mutation 邏輯。
- Route 必須有 CSRF、精確 action allowlist、3–300 字理由、fresh actor／target revalidation、safe conflict handling。
- 不允許 self-change、Officer 操作、Basic 操作、未知 role、`admin` target mutation 或藉此建立 Admin。
- 目標 inactive／disabled／blocked 時不得取得有效 Officer access；現有 status semantics 不改。
- Production 成功後 request-time access 立即反映；不得依賴舊 session role 或跨 request cache。
- Cloud-derived local preview 所有 mutation POST 仍 403；fictional demo 若要演練寫入，必須是明確獨立 demo mode，
  只連 exact local fictional DB，且 UI 清楚標示不會影響正式資料。

## 3. Management hub and role-aware navigation

- 新增 GET `/manage` 作為 server-authorized hub。Basic 403；Officer 顯示「賽務管理」；allowlist Admin 額外顯示
  「人員管理」。各卡片連至 `/manage/games` 與 `/manage/people`。
- Desktop／mobile nav 的「賽程」依 request-time actor 分流：Basic → `/future-games`；Officer／Admin →
  `/manage/games`。
- Officer／Admin 顯示「管理」並連 `/manage`；Basic 不顯示且直接存取仍拒絕。
- `/future-games` 及其他使用 shared nav 的 Portal GET pages 必須提供一致的 navigation context；不得再由個別 template
  漏傳 `can_manage_games` 造成按鈕消失。
- Officer 直接存取 `/manage/people`、pending identity、qualification 或 role mutation 仍 403；UI 隱藏不能代替 gate。

## 4. Attendance and Windows compatibility

- 修正 `apps/web_portal/app.py` Attendance update time 與
  `shared_lib/shared_module/models/games.py` formatted date 的 POSIX-only `%-m／%-d`。
- 使用 Python 3.10／Windows／Unix 都一致的明確年月日時格式，不以 locale-specific directive 猜測結果。
- `/attendance` 維持所有已能正常登入 Portal 的 active 使用者可讀，不做 Officer／Admin 限制；本 task 不擴張
  guest-only、無 Member Person 的正式出席回覆資格。
- Attendance 維持精簡 read view；empty、正常資料與安全 error state 都不得 500。
- Regression 必須至少有一條不 mock `datetime.strftime()`，在 bundled Windows Python 實際通過。

## 5. Local-preview Admin authorization parity

- 修正 Web principal 認定 preview Admin、repository 卻要求 production allowlist 的不一致。
- Preview Admin 只能在已通過 development、loopback、exact local DB、local-preview startup gate 的 runtime 被辨識；
  不得由 query、form、cookie 或任意 session role 啟用。
- Production `_require_admin` 的 allowlist、active、linked identity 規則不得放寬。
- Cloud-derived preview Admin 可讀既有 management pages，但 mutation POST 一律維持拒絕。
- 測試不得只 mock repository authorization；至少用真實 repository／PostgreSQL integration 證明 preview read parity
  與 production allowlist denial。因觸及 shared authorization／repository，final CI 需 PostgreSQL 15／16 matrix。

## 6. Mobile functional tightening and Owner QA

- 只調整 production Portal 的 nav、management hub 與 Attendance 必要密度；不做整站 redesign。
- 375／390px 無水平 overflow；nav label／destination 正確；44px touch target、keyboard focus、screen reader label 保留。
- TASK-098 lineup field／sessionStorage 行為不得退化。
- Codex 完成功能後以 fictional demo 做 Admin／Officer／Basic desktop＋390px browser QA；Work 再驗收。
- Final PR 前保留 Owner 親自走查與同一 task 小幅 CSS 收斂 checkpoint；未經 Owner UI review 不部署。

## 最小充分測試

- Route/policy matrix：Basic、Officer、allowlist Admin、Person-admin-not-allowlisted、inactive、identity mismatch。
- Officer assignment：成功升降、self、admin target、Officer caller、CSRF、reason、request replay／audit／rollback。
- Nav／hub：desktop＋mobile，所有主要 Portal GET pages，direct URL server-side deny。
- Attendance／Game Windows date regression、empty/error、active user access。
- Fictional demo offline contracts及 PostgreSQL 15／16：exact fixture seed、idempotent retry、mixed/cloud-derived deny、
  late-failure rollback、cleanup後 readback。
- Local preview真實 repository read parity、preview POST deny、production allowlist不退化。
- Web Portal full offline suite、portal-data affected suite、shared-lib rebuild／packaged runtime import、`py_compile`、
  Node syntax、Black 24.4.2／isort 5.13.2 API check、`git diff --check`、clean status。
- Hosted Python 3.10 Web Portal與 PostgreSQL 15／16 final evidence；不得以 bundled Python 3.12取代。

## Execution checkpoint

Codex 開始實作前回報五行 checkpoint：目標、核心檔案、關鍵 invariant、測試、歧義／blocker。若 fictional demo
無法與 cloud-derived preview 在資料狀態上可靠區分，或 preview Admin parity 必須放寬 production gate，立即停止交回
Work，不得以寬鬆 truncate、特殊 cookie 或 production fallback 繞過。
