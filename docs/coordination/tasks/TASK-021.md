# TASK-021：保護 Web Portal 成員配對管理端點

狀態：`planning`
優先級：P1
規劃者：Work
執行者：Codex（待 Owner 批准）
Base commit：`c022d5185cf6126ffd228b0c95b815c80ee39606`

## 1. 任務目標

保護 Web Portal 的成員配對管理頁與兩個資料修改端點，使其只允許已透過既有 LINE Login、且 Member ID 位於明確 runtime allowlist 的管理者使用；所有管理 POST 操作同時必須通過 session-based CSRF 驗證。

此任務只修改 repository並做離線驗證；不得部署、連線 production DB、發送真實 LINE／Discord通知、讀取Secret或操作Secret Manager／IAM／Scheduler。

## 2. Owner 已確認的產品規則

- 管理者暫以環境變數 `WEB_PORTAL_ADMIN_MEMBER_IDS` 的 Member ID allowlist定義。
- 未設定、空白、格式錯誤或沒有符合項目時必須fail closed，任何人都沒有管理權限。
- 不新增資料庫role欄位或migration；未來若建立正式角色模型，再獨立替換allowlist。
- 管理功能必須同時要求既有LINE登入與管理者授權；僅知道Member ID不能取得權限。
- 兩個管理POST操作必須有CSRF防護。

## 3. 已確認問題

- `GET /match-member` 直接查詢未知LINE users與所有members，沒有登入或authorization檢查。
- `POST /match-member/match` 可直接更新LINE user的`member_id`，且成功時發送Discord管理通知，沒有登入、authorization或CSRF檢查。
- `POST /match-member/ignore` 可直接將LINE user標記為ignored，同樣沒有上述防護。
- 現有LINE callback在成功登入後將`user_id`與完整`member`物件放入session，但沒有獨立`member_id`欄位。
- Web Portal目前只有demo route tests，沒有production route/auth tests。

## 4. 使用者價值

- 防止外部或一般球員讀取待配對身分資料。
- 防止未授權者竄改LINE user與Member關聯或忽略待處理使用者。
- 防止已登入管理者被第三方網站誘導送出管理POST。
- 不需正式schema變更即可先建立可部署前驗收的最小管理權限邊界。

## 5. 工作範圍

### 5.1 Admin allowlist

- 從`WEB_PORTAL_ADMIN_MEMBER_IDS`解析逗號分隔的正整數Member IDs；允許項目前後空白。
- 未設定、空白、空項目、非數字、零、負數或重複／歧義格式必須安全處理；任何整體設定錯誤均fail closed，不得部分接受。
- 解析邏輯必須是可注入／可離線測試的純helper，不在import時查DB或呼叫外部服務。
- 更新`envs/web_portal/.env_example.yaml`只加入非敏感的key與明顯placeholder／空值，不得讀取或複製真實`.env.yaml`。

### 5.2 Session與authorization guard

- LINE callback成功登入時，除既有session內容外另存最小必要的`member_id`，不得移除現有行為或擴張為session全面重構。
- 管理route必須同時確認session有既有登入身分及有效`member_id`，且該ID存在allowlist。
- 未登入：導向既有登入流程並保留安全的站內返回目標。
- 已登入但非管理者、設定缺失或設定無效：HTTP 403，不查詢管理資料、不修改DB、不發通知。
- guard應共用，不在三個route複製authorization規則。
- Demo mode仍由既有isolation先回404，不得因管理guard讓demo接觸production imports或資料。

### 5.3 CSRF

- `GET /match-member`為已授權管理者建立或重用不可預測的session CSRF token。
- `match_member.html`的兩種POST form都提交該token。
- POST缺少、空白或不匹配token時回HTTP 400，不執行任何model query／update或通知。
- 使用constant-time comparison；錯誤response不得包含預期token、收到的token、session secret或表單內容。
- 不引入大型auth／form framework；優先使用Python／Flask既有能力。

### 5.4 離線測試與CI

- 新增Web Portal管理權限離線tests，至少涵蓋：
  - allowlist：unset、blank、valid multiple IDs、whitespace、invalid／mixed-invalid皆fail closed。
  - 三個route的未登入、非管理者、缺失／無效設定拒絕路徑。
  - 管理GET只有授權者可查詢資料並產生CSRF token。
  - 兩個POST在missing／blank／wrong CSRF時都不做DB query／update或Discord通知。
  - 兩個POST在合法管理者與合法CSRF時各只執行預期操作；既有redirect與成功通知行為保持相容。
  - Demo mode的既有404 isolation不退化。
- 測試必須stub/mock ORM、Discord與外部HTTP；不得讀取`.env.yaml`、production DB或網路。
- 將新suite加入現有Python 3.10 CI；保持`contents: read`、pinned actions與既有suites。

### 5.5 文件

- 更新`apps/web_portal/README.md`說明管理allowlist、預設拒絕、CSRF契約與離線測試命令。
- Codex完成後更新report；Work驗收後更新review、`PROJECT_STATE.md`與`HANDOFF.yaml`。

## 6. 非目標

- 不新增或修改database schema、role model、migration或管理操作audit table。
- 不部署Web Portal，不查詢或修改production資料。
- 不讀取、建立、輪替或修改Secret；Member ID allowlist本身不得含姓名、LINE user ID或credential。
- 不修改Cloud Build、Docker、Secret binding、IAM或Cloud Run公開設定。
- 不處理LINE callback safe redirect、HTTP timeout、logout、session lifetime或完整Member物件session重構；另立任務。
- 不改變一般attendance、future games、roster或demo產品功能。
- 不實作Google／Apple OAuth或大型前端／auth framework。

## 7. 設計決策

- 採Member ID allowlist是暫時、可回復且無schema migration的方案；session signature保護其值，allowlist提供server-side authorization判斷。
- `WEB_PORTAL_ADMIN_MEMBER_IDS`是非機密runtime config，但仍不得把真實環境值提交repository。
- Authorization必須在CSRF與任何資料查詢之前執行；CSRF必須在POST業務查詢／修改之前執行。
- 不接受「所有已配對Member都是管理者」，避免一般球員取得身分配對權限。
- 既有Discord成功通知只允許在授權與CSRF均通過、且實際完成match後保留；拒絕路徑不得發送。

## 8. 驗收條件

- 三個管理route均有共用的登入與admin authorization guard。
- Allowlist預設關閉且invalid config整體fail closed。
- 未登入者不能讀取管理資料；非管理者回403。
- 兩個POST缺少或錯誤CSRF時回400且零資料／通知副作用。
- 合法管理流程保持現有配對、忽略、redirect與成功通知契約。
- Demo mode、既有LINE Login及一般頁面未被移除或降低安全性。
- 新舊離線測試與Python 3.10 CI通過。
- `git diff --check`及受影響模組compile/import check通過。

## 9. 驗證命令

```powershell
python -m unittest discover -s apps/web_portal/tests -v
python -m unittest discover -s functions/line_webhook_handler/tests -v
python -m unittest discover -s apps/game_broadcast_service/tests -v
python -m unittest discover -s apps/notify_cronjob_service/tests -v
python -m unittest discover -s functions/update_game_schedule/tests -v
python -m unittest discover -s tools/tests -v
python -m compileall -q apps/web_portal
git diff --check
git status --short
```

本機若不是Python 3.10，可用repository可用runtime做離線驗證，但最終必須取得GitHub-hosted Python 3.10 CI成功證據。

## 10. 影響範圍與依賴

- 預估檔案：`apps/web_portal/app.py`、管理template、新auth/CSRF helper、Web Portal tests、README、`.env_example.yaml`與CI workflow。
- 依賴：既有Flask session、`secrets`與LINE Login session；不新增第三方dependency。
- 主要風險：allowlist值若未部署會安全地鎖住所有管理者；未來production deployment必須另行確認設定與rollback，但不屬本任務授權。

## 11. PR 工作包（待 Owner 批准）

若Owner接受此任務，建議同時批准Codex：

- 建立`codex/protect-web-portal-member-matching` branch。
- 建立描述性local commits、push並建立Draft PR。
- 執行離線測試與GitHub Actions，於同一PR更新Codex report及交棒文件。

仍不包含ready／merge、deployment、production request、正式通知、production DB、Secret／IAM／Scheduler、schema或其他雲端操作；merge須由Owner在Work驗收後另行批准。
