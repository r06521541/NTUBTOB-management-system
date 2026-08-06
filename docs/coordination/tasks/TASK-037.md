# TASK-037：最小化 Web Portal 登入 Session

狀態：`ready_for_codex`
優先級：P1 security／privacy
規劃角色：Work
執行角色：Codex
Base commit：`fee79c9`

## 1. 目標

讓 production Web Portal 的 Flask cookie session 只保存驗證登入流程與授權所需的最小識別資料，不再保存完整 `Member` dataclass 或未被 application 使用的 LINE `display_name`。Attendance 頁面改在 request-time 依 `member_id` 重新取得 Member，避免姓名等資料進入可由browser解讀的signed-but-not-encrypted cookie，也避免長期使用 stale Member snapshot。

本任務只修改 repository與離線測試，不改 schema、LINE provider、Secret、IAM或production。

## 2. 已確認現況

- LINE callback 成功後目前寫入 `user_id`、`member_id`、完整 `member` 物件與 `display_name`。
- `Member` 是 dataclass SQLAlchemy model，至少含 `id` 與 `name`；Flask cookie session有簽章但不是加密儲存。
- `/attendance` 目前直接使用 `session['member']`，形成cookie內Member snapshot依賴。
- Repository搜尋顯示 production application不需要從session讀取`display_name`；現有測試只用它確認OAuth錯誤不清除既有identity。
- `/game-roster` 的TASK-035 guard只需要有效`user_id`與`member_id`，不依賴完整Member。
- Demo使用獨立的`demo_member`虛構session資料；本任務不得破壞development-only demo。

## 3. 實作範圍

### 3.1 新登入只保存最小identity

- LINE callback成功配對後只保存有效`user_id`與正整數`member_id`。
- 不再將完整`Member`或LINE `display_name`寫入session。
- callback仍須先完成既有LINE response validation、LineUser與Member配對，不能因最小化session降低authentication boundary。
- 重新登入時要主動移除可能已存在的legacy `member`與`display_name` keys。

### 3.2 平順清理既有session

- 對已簽發的v2 session建立小型、明確的legacy identity cleanup，使合法`user_id`／`member_id`可保留，不強迫所有使用者登出。
- Cleanup只移除精確keys `member`與`display_name`，不得使用`session.clear()`，不得清除OAuth nonce、CSRF、return path或demo keys。
- Cleanup須在一般production request也能觸發，讓舊cookie下一次回應重新簽發為最小payload；不得依賴使用者重新登入才清除。
- 既有invalid OAuth state仍只清除OAuth transaction資料並保留`user_id`／`member_id`；legacy fields可由共用cleanup移除。

### 3.3 Attendance request-time Member lookup

- `/attendance`與其入口使用現有member authentication boundary，不再以`session['member']`判定登入。
- 合法session依`member_id`呼叫既有`Member.search_by_id`，再把fresh Member傳入template。
- Member不存在時須fail closed：清除production identity keys，停止Game／attendance查詢並顯示既有未核可／需重新登入的安全狀態；不得形成redirect loop或500。
- 畸形session須在Member、Game、attendance或HTTP呼叫前由guard拒絕。
- 不在本任務新增每個protected route的request-time DB revalidation；完整member lifecycle／停用規則留待RBAC任務。

### 3.4 Tests與文件

- 先建立可重現cookie中legacy Member／display_name的回歸測試，再實作修正。
- 至少涵蓋：
  - 成功callback session只含必要identity，不含`member`／`display_name`。
  - 舊session在一般request保留`user_id`／`member_id`並移除兩個legacy keys。
  - cleanup不清除OAuth nonce、CSRF、safe return path及demo keys。
  - invalid OAuth state保留最小identity，但legacy keys不再存在。
  - attendance以member_id取得fresh Member並維持既有成功內容。
  - Member不存在時清除identity、停止Game／attendance／HTTP，安全回應且不loop。
  - 畸形session在資料與外部呼叫前fail closed。
  - roster、admin、CSRF、LINE Login、cookie policy與demo suites不退化。
- 更新Web Portal README，說明session只保存opaque identity IDs，Member資料request-time取得；不要宣稱cookie內容已加密。

## 4. 非目標

- 不新增role、approval、disabled欄位，不改schema或migration。
- 不實作完整member／officer／admin RBAC或帳號停用流程。
- 不更換server-side session backend，不新增Redis／Supabase session table。
- 不改session cookie名稱、Secret key、lifetime、SameSite或LINE OAuth state設計。
- 不修改shared_lib model介面、其他服務、通知、cache或crawler。
- 不讀取`.env.yaml`、Secret payload或production DB。
- 不部署、不呼叫production、不修改Secret／IAM／Cloud Run、不發送LINE／Discord通知。

## 5. 驗收條件

- 新舊production session均不再保存完整Member與LINE display name。
- 既有合法登入者可平順遷移，不因cleanup被整體登出。
- Attendance只從fresh request-time Member取得姓名等資料。
- Member不存在或session畸形時，在Game／attendance與外部呼叫前fail closed。
- TASK-029／032 OAuth state、versioned cookie、legacy cookie expiry與logout-CSRF保護不退化。
- Demo session與全部離線Web Portal測試通過。

## 6. 驗證命令

```powershell
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q apps/web_portal
python tools/deploy_web_portal.py
git diff --check
git status --short
```

若本機缺少全域Python，使用工作區bundled Python；兩項既有Windows `make`／`sh` skip須如實回報。

## 7. 授權邊界

Owner已批准建立TASK-037並交棒Codex。Codex可執行repository-only實作、離線測試與描述性本機commit，並更新report／PROJECT_STATE／HANDOFF交回Work。此指示未單獨批准新的PR工作包，因此不得push、建立PR、merge或部署；完成本機驗收後由Owner另行決定PR流程。
