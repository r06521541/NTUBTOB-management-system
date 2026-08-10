# TASK-097：Local production-shaped Portal preview

task_type: delivery
delivery_group: phase-d-local-cloud-data-preview
requires_independent_pr: true
status: changes_requested
owner: work
codex: codex

## 使用者價值

讓 Owner 能在本機瀏覽 TASK-096 正式 Portal UI，使用來自雲端 PostgreSQL／Supabase、但經固定欄位過濾與
去識別化後的 production-shaped 資料；本機程式不得直接讀寫 production，也不得依賴真實 LINE Login。

## 核心架構

`fixed read-only export → private local bundle → validation/pseudonymization → localhost PostgreSQL → localhost-only preview identity → production Portal templates`

雲端匯出與本機預覽是兩個安全邊界：repository 只交付受控 SQL／匯出契約、validator、pseudonymizer、importer、
preview gate、測試與 runbook。本 task 不授權實際連線 Supabase 或執行匯出；真正執行前須由 Owner 看過 exact SQL、
table／column allowlist、輸出位置與保存期限後另行批准。

## 範圍

- 以固定唯讀 SELECT 定義 Game、Member、Attendance、Person、Identity、Qualification 的必要資料契約。
- 匯出只允許 UI 與關聯完整性所需欄位；排除密碼、token、Secret、私人備註、醫療資訊與原始 provider subject。
- 建立私有 local bundle manifest 與逐檔 checksum；bundle 與衍生資料必須被 Git ignore，且不可出現在 log／report。
- 建立 deterministic pseudonymization：姓名與內部識別值轉為穩定 surrogate，同時保存跨表 foreign-key 關係、
  row cardinality、game/attendance semantics 與必要時間欄位。
- 建立 importer，只接受既有 `require_local_database_url` 所允許的 `ntubtob_portal_local` localhost database，驗證
  schema revision `0004_phase_c_identity_lifecycle`、manifest、欄位、型別、row limits 與 foreign keys。
- Import 必須使用單一 transaction；任何驗證或寫入失敗完整 rollback，不得留下部分資料。
- 建立雙閘門 localhost preview identity；只能在 development＋explicit preview flag 下啟用，並綁定 loopback host。
- Preview 使用正式 Portal route／template／repository contract，不讀 Demo fixture；第一版所有 mutation UI 為唯讀或
  fail closed，不呼叫 LINE、Discord、weather、crawler 或其他外部服務。
- 提供 Windows PowerShell runbook，使用 Codex bundled Python executable 與既有 localhost PostgreSQL Compose。

## 安全 invariant

- 任意 Supabase／remote DSN、非 `ntubtob_portal_local` database、未知 table／column、revision 不符、checksum 不符、
  malformed bundle 或超出 row limit 都必須在寫入前 fail closed。
- Local preview flag 在 production、非 loopback bind、缺少 development gate 或設定值不精確時必須 fail closed。
- Preview session 不使用真實 LINE user、production cookie、allowlist admin ID 或 Secret；測試只使用明顯的虛構身份。
- 不得在 source、fixture、test output、exception、screenshot metadata 或 Git 中留下 production row、DSN、password、
  provider subject 或可還原個資的 pseudonymization seed。
- 不修改 production schema、資料、RLS、Secret、IAM、Scheduler 或 cloud resource；不部署、不發送真實通知。

## 非目標

- 不讓本機 Portal 直接連 production database。
- 不建立 production replica、持續同步、CDC、排程匯出或長期資料湖。
- 不在第一版支援本機 attendance／profile／identity／qualification 寫入模擬。
- 不新增正式登入 provider，不修改 LINE Developers callback，不降低現有 session／CSRF／authorization 邊界。
- 不實作 Event／Activity production domain。

## 最小充分測試

- Importer unit tests：allowlist、型別、row limit、checksum、revision、remote URL rejection、transaction rollback、
  deterministic mapping 與 cross-table relationship preservation。
- PostgreSQL 15／16 integration：從明顯虛構 cloud-shaped bundle 匯入、重跑／衝突行為、失敗 rollback 與 readback。
- Web Portal tests：preview gate truth table、loopback-only bind、preview identity、正式 route render、mutation fail-closed、
  CSRF／capability 不退化及 zero external calls。
- 完整 `apps/web_portal/tests`、受影響 `tests/portal_data`、`py_compile`、逐檔 formatter check、`git diff --check`。
- Hosted CI 提供 Python 3.10 與 PostgreSQL 15／16 最終證據；本機 bundled Python 3.12 僅作 targeted verification。

## 驗收條件

- Owner 依 runbook 可在不提供 Codex credential 的前提下產生受控私有 export，並在本機完成 validate、
  pseudonymize、transactional import 與 Portal preview。
- Dashboard、賽程、出席、People、Person detail 與 Qualification 頁面使用正式 route/template 顯示
  production-shaped、去識別化資料。
- 原始與衍生 bundle 均不進 Git；停止／清理程序只針對精確 local preview artifacts 與 Compose named volume。
- 測試證明 production／remote／external-effect 邊界 fail closed，且沒有 schema migration 或 production mutation。

## Execution checkpoint

開始實作前，Codex 必須回報五行 checkpoint：目標、核心檔案、關鍵 invariant、最小充分測試、歧義／阻塞。
