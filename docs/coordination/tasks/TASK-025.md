# TASK-025：多元活動與複合行程 Demo

狀態：`ready_for_codex`
優先級：P2 product prototype
規劃者：Work
執行者：Codex
Base commit：`9f44165`

## 1. 任務目標

在既有development-only Web Portal demo中建立「多元活動管理」產品原型，讓具幹部prototype身分的Demo使用者可以建立、編輯與預覽聚餐、旅遊／移地活動、友誼賽、OB賽、練球及其他隊務活動；一個Event可以包含多個Activity，例如週末旅遊包含交通、住宿、聚餐與三場比賽。

此任務用來驗證產品願景，不實作正式持久化。所有新增、編輯、發布狀態及出席回覆只存在Flask session；不得修改models／schema、連線DB、呼叫crawler／LINE或影響production routes。

## 2. 核心產品假設

### 2.1 Event與Activity

- `Event`代表一次完整活動，至少包含名稱、類型、起訖日期、地點摘要、說明、狀態與建立者顯示。
- Event類型：`game_day`、`practice`、`meal`、`trip`、`meeting`、`other`。
- Event狀態：`draft`、`published`、`cancelled`。Demo不真的通知任何人。
- `Activity`代表Event內的行程，類型：`game`、`meal`、`transport`、`lodging`、`gathering`、`free_time`、`other`。
- Activity至少包含標題、日期、開始／結束時間、地點、說明與排序。
- 單場友誼賽也採一個Event＋一個game Activity，UI可提供快速建立流程。

### 2.2 比賽來源

- Game activity來源分為`league_imported`與`manual`。
- Repository-local fixture提供至少一場虛構聯盟匯入賽事；它在builder中可被加入Event，但其聯盟識別、對手與開賽時間需呈現唯讀，不可被手動流程覆寫。
- 幹部可新增manual game，例如友誼賽或OB賽，填寫對手、主客場、球場及集合時間。
- 不呼叫現有crawler、不讀正式`games` model，不進行重複賽事判定；畫面需標示正式版仍需處理同步與去重。

### 2.3 幹部prototype權限

- Demo member標示`officer` prototype角色，只有該demo session能進入builder routes。
- Guard必須獨立於production admin allowlist，不能呼叫或降低TASK-021 `/match-member`安全邊界。
- 測試可直接建立非officer demo session，確認builder GET／POST皆403且不改state。
- 此角色只作產品原型，不代表正式角色模型或授權決策。

### 2.4 草稿、發布與取消

- 建立Event時先存為draft。
- 幹部可預覽完整活動時間軸，再執行「發布Demo」；published Event才顯示於一般活動列表。
- 已發布Event可回到draft或標記cancelled，但每次狀態轉換必須經CSRF與allowlist。
- 發布、取消只改session並顯示明確banner：「不會發送LINE通知」。
- 不做第二人覆核；文件與UI需列為正式版待決策。

### 2.5 兩層出席

- Event層支援`attending／tentative／declined`。
- 具多個可回覆Activities時，提供「全部參加」套用，再允許逐項覆寫。
- Activity層支援`attending／tentative／declined／not_applicable`。
- 交通與住宿可各自回覆；不得收集真實地址、證件、健康或付款資料。
- Event與Activity回覆都只存在session，並在Event detail顯示摘要與尚未完成項目。

## 3. 使用者流程

### 3.1 一般成員

1. 從Dashboard或bottom／desktop navigation進入「活動」。
2. 查看published與cancelled活動；draft不可見。
3. 開啟活動詳情，查看時間軸、來源badge與注意事項。
4. 回覆整體活動；若是複合活動，再個別調整比賽、住宿、交通或聚餐。
5. 回到活動列表或Dashboard看到自己的狀態與待辦更新。

### 3.2 幹部

1. 從幹部工作台進入Event Builder。
2. 以模板快速建立：單場友誼賽、聚餐、週末移地活動；也可從空白開始。
3. 編輯Event基本資料。
4. 新增、編輯、刪除及上移／下移Activities。
5. 加入虛構league-imported game或建立manual game。
6. 預覽mobile timeline後發布Demo。
7. 一般活動列表立即出現已發布Event，但沒有外部通知。

## 4. 必要頁面與UI

- 活動列表：類型、日期範圍、地點、狀態與我的回覆；支援all／game／trip／meal等安全filter。
- 活動詳情：Event摘要、activity timeline、來源badge、兩層出席與prototype標示。
- 幹部活動工作台：draft／published／cancelled數量、建立入口及現有event cards。
- Event基本資料表單。
- Activity編輯器：新增／編輯／刪除／排序。
- 預覽／發布頁或等效清楚流程。
- Empty、validation error、not found與權限拒絕狀態。
- 375px附近可操作；長時間軸、表單與actions不得造成頁面級橫向捲動。

可在既有TASK-024的Dashboard、幹部頁與navigation加入入口，但不得破壞原本賽事作戰中心流程。

## 5. Session資料與安全限制

- 所有資料只能是JSON-compatible primitives，禁止ORM objects。
- Session Event上限5個，每個Event最多12個Activities；標題／地點／說明等均需合理長度限制，以避免cookie無限制膨脹。
- ID只能由server產生且具明確demo prefix；不得接受client提供任意ID。
- 所有POST routes必須具demo gate、登入、officer guard（管理操作）、CSRF、allowlist與PRG。
- 刪除、排序、狀態轉換與回覆需驗證Event／Activity存在且屬於正確Event。
- Jinja維持autoescape；測試需放入HTML-like輸入確認不被執行。
- 不使用query／header／cookie繞過demo雙重gate。
- 不新增依賴；優先使用標準函式庫與既有Flask／Jinja。

## 6. 虛構種子資料

至少提供：

- 一個published週末移地Event，包含交通、住宿、聚餐及三場比賽。
- 一個published聚餐Event。
- 一個draft OB賽或友誼賽Event，只在幹部工作台可見。
- 至少一場`league_imported` game activity及一場`manual` game activity。

所有名稱、球場、旅館、對手與集合點必須明顯虛構，使用`.invalid`連結或disabled actions，不使用真實隊員個資。

## 7. 明確非目標

- 不修改`shared_lib`、SQLAlchemy models、Supabase schema、migration或正式資料。
- 不讀取現有production games／members／attendance，不呼叫crawler或任何外部API。
- 不實作正式RBAC、幹部升降、第二人覆核或audit persistence。
- 不發LINE／Discord／email／push，不做通知排程或實際預覽收件人。
- 不實作付款、住宿訂房、地圖導航、真實共乘、健康／緊急聯絡資料。
- 不部署、不操作Secret／IAM／Cloud Run／Scheduler。
- 不push、不建立PR；只允許既有描述性local commits。

## 8. 必要測試

至少涵蓋：

- Demo gate與匿名保護涵蓋所有新增routes。
- Officer guard：一般demo member的builder GET／POST皆403且零session mutation。
- 三種template建立、空白建立、Event欄位allowlist／長度／日期範圍validation。
- Activity新增／編輯／刪除／排序，跨Event activity ID不可操作。
- Event／Activity數量上限fail closed且不破壞既有state。
- League-imported fields在builder不可被manual payload覆寫。
- Draft不出現在一般列表；publish／cancel／回draft轉換與CSRF。
- Event整體回覆、全部參加及逐項override，跨Event回覆不污染。
- HTML-like輸入被escape；invalid IDs／filters／status回400或404且不改state。
- 完整流程：幹部建立週末Event→加入三場比賽與其他活動→預覽→發布→一般活動列表→成員兩層回覆。
- Patch DB models及HTTP clients為呼叫即失敗，所有新demo流程仍通過。
- TASK-024既有33項tests與TASK-021／022安全tests不退化。

必要命令：

```text
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q apps/web_portal
git diff --check
git status --short
```

## 9. 驗收條件

- Owner可在local demo完成幹部建立、編排、預覽、發布與一般成員回覆的完整流程。
- 週末Event能清楚包含三場比賽與交通／住宿／聚餐，且時間軸在手機可讀。
- League-imported與manual games清楚區分，匯入fixture不可被builder覆寫。
- Draft與published可見範圍正確；所有管理POST具officer guard與CSRF。
- 兩層出席狀態與跨頁摘要一致，reset可回復種子狀態。
- 所有資料與mutation僅存在demo session，沒有DB／schema／external side effects。
- 完整Web Portal tests、compile及diff checks通過。

## 10. 停止條件與交付

只有需要Secret、production／Supabase DB、schema、shared_lib、外部API、正式通知或降低既有安全邊界時才停止；其他prototype細節採安全合理預設持續完成。

完成後：

- 撰寫`docs/coordination/reports/TASK-025-CODEX.md`。
- 使用描述性local commits，TASK編號放body/footer。
- 更新`HANDOFF.yaml`為`ready_for_review / work`。
- 不push、不建立PR、不部署。

