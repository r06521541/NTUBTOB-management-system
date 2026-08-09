# TASK-024：Web Portal Team Operations Demo

狀態：`awaiting_owner_approval`
優先級：P2 product prototype
規劃者：Work
執行者：Codex
Base commit：`919cb5c`

## 1. 任務目標

在既有Flask／Jinja development-only demo上建立一套可連續操作的「球隊賽事作戰中心」原型，讓Owner能在local從Dashboard進入賽事，完成出席細節、共乘、裝備分工、Game Day查看、個人設定與幹部摘要等主要流程，藉此驗證未來值得正式建模的產品規則。

本任務是可離線驗收的產品prototype。所有寫入只存在demo session，不修改正式schema／models、不連線DB、不呼叫外部服務，也不得接入production routes。

## 2. 已確認現況

- TASK-012已建立雙重fail-closed demo gate、虛構member／games、Dashboard、賽程、詳情、個人與等待核可頁。
- Demo出席回覆目前只有`attending／declined／tentative`，寫入Flask session。
- 現有頁面已有mobile-first共用layout、cards、status badges與bottom navigation。
- TASK-021／022已修改production管理權限與deployment boundary；本任務不得改動或繞過。
- TASK-023確認Web Portal production deployment仍受兩個runtime Secret resources阻擋；本任務不解除該blocker。

## 3. 產品範圍

### 3.1 Dashboard營運摘要

- 下一場賽事卡加入回覆截止倒數、集合時間、球衣顏色與人力狀態。
- 顯示「我的待辦」：未回覆、尚未選交通方式、尚未認領裝備等session-derived項目。
- 顯示虛構置頂公告及近期賽事異動摘要。
- 顯示守位人力摘要，例如投手／捕手／內野／外野是否足夠；規則必須集中於可測試helper，且標示為demo估算。

### 3.2 賽程檢視

- 保留既有列表並新增月曆／時間軸式檢視；不用JavaScript framework。
- 支援session-safe篩選：全部、未回覆、已出席、主場／客場。
- 提供單場`.ics`下載，使用標準函式庫產生，Asia/Taipei時間與escaping需有測試。
- 不建立Google Calendar API整合；可提供一般calendar下載按鈕。

### 3.3 出席細節

- 出席狀態外增加：準時、晚到、早退、僅觀賽。
- 可選預計抵達時間、守位偏好與簡短公開備註。
- 所有欄位採allowlist、長度限制與安全預設；未知game／invalid status／畸形時間／過長備註明確拒絕。
- 詳情頁需清楚區分我的回覆與全隊虛構名單，不得讓輸入被當成HTML執行。

### 3.4 Game Day模式

- 新增手機優先的單場Game Day頁：集合／開賽時間、球場、導航demo link、球衣、天氣占位、最新公告。
- 顯示打序／守位板prototype、先發／候補與人力缺口；只能讀repository-local虛構資料。
- 顯示比賽日checklist與裝備認領：球、球棒、捕手裝備、急救包、飲水。
- Demo使用者可以session-local認領／取消認領裝備，採POST/redirect/GET。
- 提供「比賽日大字模式」或等效高可讀狀態，不要求動畫。

### 3.5 交通與後勤

- Demo使用者可選自行前往、需要接送、可提供座位。
- 可提供座位時可選虛構集合點與座位數；需要接送時只選虛構集合點。
- 顯示全隊虛構共乘摘要，不收集真實電話、地址或定位。
- 顯示費用與付款狀態的唯讀prototype，不實作付款或session寫入。

### 3.6 個人頁與設定

- 顯示背號、主要／次要守位、打投慣用手與本季虛構摘要。
- 通知偏好可在session切換：賽事邀請、截止提醒、異動／取消；明確標示不會真的發送通知。
- 保留LINE connected及Google／Apple disabled prototype。
- 提供清除demo個人化資料／重置demo的明確操作。

### 3.7 幹部工作台prototype

- 新增獨立demo頁呈現未回覆、待核可、人力缺口、裝備缺口與通知預覽。
- 只呈現虛構資料；不得沿用或呼叫production `/match-member` routes。
- 通知預覽不可提供真正發送按鈕；必須標示為prototype／不會發送。
- 不實作角色權限；頁面須標示未來將由幹部／管理員角色控制。

## 4. 工程設計限制

- 延續Flask／Jinja與local CSS，不加入React、Vue、Node build chain或大型前端／CSS framework。
- `demo_portal.py`若過度集中，可拆成小型repository-local helpers／providers，但不得全面重寫`app.py`。
- Demo狀態只保存JSON-compatible primitive data；不得將ORM object放入session。
- 對POST demo actions採CSRF防護。可以建立demo專用、session-backed token helper；不得降低TASK-021 production CSRF boundary。
- Session資料需有明確初始值、validation與reset path；避免cookie無限制膨脹。
- 所有日期時間使用有timezone資料或明確Asia/Taipei規則，不依賴主機local timezone或import-time `now`。
- `.ics`使用標準函式庫實作，不新增calendar套件；需正確Content-Type、Content-Disposition、CRLF及文字escaping。
- CSS維持375px左右無頁面級水平捲動；表格在手機需轉為cards或安全水平容器。
- 所有demo姓名、地點、對手、公告、集合點與費用均須明顯虛構。

## 5. 非目標

- 不修改production routes的LINE Login、member matching、attendance或game roster行為。
- 不修改`shared_lib`、models、schema、migration或production data。
- 不建立正式角色權限、幹部權限、通知偏好持久化或audit log。
- 不實作真正LINE／Google／Apple OAuth、通知發送、地圖API、天氣API、付款或共乘媒合。
- 不操作Secret、IAM、Cloud Run、Cloud Build、Scheduler或任何production資源。
- 不部署、不呼叫production URL、不連production／Supabase DB。
- 不push、不建立PR；Owner只延續既有local commit授權，外部PR工作包需另行批准。

## 6. 必要測試

新增或擴充離線tests，至少涵蓋：

- 既有demo雙重gate truth table與匿名保護不退化。
- Dashboard待辦、人力缺口與session變化一致。
- 賽程篩選allowlist及未知filter安全行為。
- `.ics`時區、escaping、headers、未知game與無外部呼叫。
- 出席細節成功路徑，以及invalid status／arrival／position／過長note拒絕。
- 裝備認領／取消、交通設定、通知偏好與reset皆只改session。
- 所有POST action缺少／錯誤CSRF token拒絕且不改session。
- Game Day、個人頁、幹部prototype主要內容與安全標示存在。
- Patch DB/model、HTTP、LINE、Discord、crawler與weather為「呼叫即失敗」，完整主要navigation仍通過。
- HTML responsive contracts：viewport、navigation、touch target class／結構、無已知固定寬度破版。
- 既有LINE routes與TASK-021管理安全tests維持通過。

至少執行：

```text
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q apps/web_portal
git diff --check
git status --short
```

若有可用browser automation，可額外以375×812與desktop viewport做local visual smoke並保存非敏感截圖；沒有工具時不得宣稱視覺實跑通過。

## 7. 驗收條件

- Owner能用README既有一條指令啟動，從Dashboard完成至少一條連續流程：回覆出席細節→設定交通→認領裝備→Game Day查看→回到Dashboard看到待辦更新。
- 月曆／列表與單場`.ics`可離線使用。
- 個人通知偏好、reset與幹部工作台均清楚標示prototype，不產生外部副作用。
- Demo gate關閉時所有新增demo routes仍fail closed。
- 所有寫入只存在session，沒有DB／schema／external API呼叫。
- 375px附近沒有已知頁面級橫向破版，鍵盤focus與表單label合理。
- 既有Web Portal tests全部通過，新增行為有成功與重要失敗測試。
- 無production、Secret、deployment、shared library或其他service變更。

## 8. 建議實作順序

1. 擴充虛構domain data與純helper，先補unit tests。
2. 建立session state schema、CSRF與validation helpers。
3. 實作出席／交通／裝備／偏好actions及route tests。
4. 實作Dashboard、games、Game Day與officer workspace templates。
5. 實作`.ics`與calendar／filter UI。
6. 完成responsive／accessibility polish、README與全套回歸。
7. 撰寫`docs/coordination/reports/TASK-024-CODEX.md`並更新handoff。

## 9. 安全停止條件

只有遇到下列情況才停止並交回Owner；其他小型產品文案或虛構資料選擇應採安全合理預設持續完成：

- 需要Secret、production credential、外部API或production DB才能完成。
- 需要修改schema／shared models或正式通知行為。
- 需要降低demo雙重gate、production auth、CSRF或公開邊界。
- 發現既有未提交變更與本任務修改同一檔案且無法安全保留。

## 10. 交付要求

- 使用描述性local commits，TASK編號放body/footer。
- 完成報告須列出使用者可見行為、設計取捨、實際tests、未驗證項目、prototype限制及所有變更檔案。
- 完成後更新`HANDOFF.yaml`為`ready_for_review / work`；不得push、建立PR或部署。
