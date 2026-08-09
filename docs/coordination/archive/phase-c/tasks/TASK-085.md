# TASK-085：Phase C 零管理員安全 bootstrap

## 目標

在不降低 Phase C 登入／管理授權邊界、不中斷既有服務且不修改 schema 的前提下，建立一次性、可稽核、可重試的零管理員復原流程，將 Owner 已確認的 pending LINE identity 配對至既有 allowlisted Member／Person。同時修正 TASK-084 inventory 的 pager timeout，讓後續 Stage B 證據可完整輸出並正常 `ROLLBACK`。

本任務只做 repository/local 實作、隔離 PostgreSQL 演練、測試、commit、push、report 與 handoff。不得連 production、讀 private env／Secret、部署、變更 flags／traffic／IAM／Scheduler或執行正式資料 mutation。正式 bootstrap 必須由 Work 另行產生 exact execution package，經 Owner 明確批准後才可執行。

## 已確認 production finding

- Schema revision 為 `0004_phase_c_identity_lifecycle`。
- 197 People／197 Members、56 reliable linked LINE identities、56 active team players、1,651 attendance replies；已取得的 identity／Member-Person／qualification drift 與 duplicate 指標皆為零。
- `active_linked_allowlisted_admin_count=0`，與 Owner 登入後被導向 pending review 一致；allowlist 不得繞過 pending identity。
- 原定 safe ignore／unignore candidate counts均為零，故不得執行原 smoke。
- 查詢輸出被pager暫停，超過30秒後server以idle-in-transaction timeout終止連線並自動rollback；沒有production mutation。該transcript缺少required metric與正常`ROLLBACK`，不得作final evidence。

## Scope

1. **Pager-safe inventory**
   - 在任何 `BEGIN`／query 前固定關閉 psql pager，禁止依操作人環境自動分頁。
   - SQL、runbook、checksum與verifier使用同一契約；新增足量輸出仍不進pager、可抵達明確`ROLLBACK`的真實psql regression。
2. **Read-only bootstrap discovery**
   - 候選資料只可在執行者本機互動顯示，不寫入repository／report／log；正式文件只保存aggregate classification。
   - 候選必須是LINE provider、pending、無Person、具相鄰legacy row且可由既有domain approval安全連至一個Member／Person。
   - 使用repository-external identity reference、Member ID、reason與opaque request ID；provider subject、姓名、LINE profile或Member ID不得進argv、repository、CI artifact或一般log。
   - 零候選、多候選、target不明、legacy／Member／Person drift均fail closed。
3. **Zero-admin bootstrap transaction**
   - 重用／抽取既有`approve_member` domain invariants，不建立旁路式ad-hoc update。
   - 以transaction-level advisory lock序列化；鎖內重新確認active linked allowlisted admin精確為0，且target Member ID確實在完整有效allowlist中。
   - 鎖定exact pending identity、legacy LINE row、Member、Person及相關qualification／thread；拒絕blocked／disabled Person、已連結／ignored／歧義資料或資格drift。
   - 原子完成identity linked、legacy member link、Person active、必要team_player invariant、review thread close與單一append-only audit；不得變更其他Person／Member／identity／qualification／attendance。
   - request ID唯一；相同request ID＋相同target重試必須零增量並回傳相同結果，任何state drift則fail closed。
   - 一旦已存在至少一位active linked allowlisted admin，bootstrap永久拒絕；後續一律走一般admin route。
4. **Execution package與post-check**
   - 產生checksummed fail-closed operator contract；識別輸入只在互動式runtime提供，不進SQL statement text、argv或transcript。
   - post-check要求active linked allowlisted admin由0變1、identity／legacy link／Person／qualification一致、audit精確+1、其他aggregate及attendance不變；retry零增量。
   - 執行失敗依transaction rollback；commit後若驗證不一致，只能走已測試domain forward recovery，不得刪audit或ad-hoc SQL修補。

## Non-goals

- 不開啟identity maintenance、不部署Web Portal、不改Phase C／freeze flags。
- 不變更schema、migration、RLS、Secret、IAM、Scheduler或通知行為。
- 不核可一般使用者、不批次配對、不實作新角色／活動功能。
- 不以allowlist直接繞過pending，也不讓pending identity自我授權。

## 必要測試

- Python 3.10 domain tests：成功、retry、zero/multiple admin boundary、錯誤allowlist、錯誤identity/member、blocked/disabled、legacy drift、audit/qualification failure rollback與concurrency。
- 隔離PostgreSQL 15／16 integration：constraints、advisory lock、atomic audit、same-request idempotency、兩個concurrent bootstrap只能一個成功。
- 真正PostgreSQL 16 psql client測試pager-off、互動式parameter binding與完整`ROLLBACK`。
- 受影響Web Portal／portal_data tests、compileall、Black formatter API、`git diff --check`、`git status --short`。

## 驗收條件

- 不存在active admin時，只有Owner精確指定且通過全部invariants的pending identity能被bootstrap。
- 已存在active admin或資料有任何歧義時無資料改變。
- 同一request重試不新增audit或重複qualification；concurrent執行不會建立兩個bootstrap admins。
- inventory不再因pager停留於read-only transaction。
- 所有production識別資料與Secret保持repository外；本任務沒有production access或mutation。

## Base commit

`f09c13eadc1d88c49aaf83a3362ab2a563ad8e7a`
