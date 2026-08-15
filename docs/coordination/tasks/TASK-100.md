# TASK-100：Owner UI refresh release readiness

task_type: delivery
delivery_group: phase-d-owner-ui-refresh
requires_independent_pr: true
status: in_progress
owner: work
codex: codex

## 使用者價值

將 Owner 在 fictional localhost workflow 完成的整批 Portal UI、角色、人員管理、出席、試排守位與 Dashboard
調整，收斂成下一次 Web Portal production deployment 可驗收、可 rollback 的單一 delivery。

## 交付範圍

- Production Portal UI 與 responsive navigation；Basic 顯示「一般使用者」、Officer 顯示「幹部」。
- Admin 建立 Member、basic/officer 轉換、Person/qualification/admin note 與 identity dialog UI。
- `/attendance`、Dashboard、Game detail/command center/insights，以及 sessionStorage-only lineup lab。
- Fictional demo seed 與 Windows-safe Game 日期、目前球隊別名及訊息 caller 相容。
- Dashboard 賽前兩日 08:00（Asia/Taipei）至比賽結束的 CWA 天氣顯示；缺少設定或 API 失敗時安全隱藏。

## 固定邊界

- Database revision 固定 `0004_phase_c_identity_lifecycle`；不得新增 schema、migration 或正式資料異動。
- Production Admin authority 只來自 `WEB_PORTAL_ADMIN_MEMBER_IDS`；Person `admin` 不取代 allowlist。
- Officer 只取得 bounded Game management；People、identity、qualification、audit 與 notification 管理仍拒絕。
- Lineup 只存在 browser sessionStorage；不新增 server persistence、Game/Roster mutation 或外部副作用。
- Cloud-derived local preview 的 POST 持續 fail closed；fictional demo 不連 production、Supabase 或 Secret。
- 本 task 可依既有 standing authorization commit、push、建 ready PR、追 CI 及 merge；正式 deployment、Secret、IAM、
  Scheduler、production traffic、正式資料與真實通知仍需 Owner 對 exact target 明確批准。

## Release 驗收

- Web Portal full suite；portal-data offline；所有受 shared library 影響的 broadcast、notify 與 webhook callers。
- Hosted Python 3.10、Black 24.4.2/isort、packaged shared library import 與 deployment preflight。
- Basic/Officer/Admin route matrix、fresh principal、CSRF、preview POST deny、未知角色 fail closed。
- Jinja parse、JavaScript syntax、desktop/390px UI evidence、`git diff --check`、無 Secret/schema artifact。
- PR 合併後另提出 exact commit、Cloud Run service/region、rollback revision、Secret resource references metadata 與
  post-deploy smoke/rollback package；未經批准不得執行 deployment。
