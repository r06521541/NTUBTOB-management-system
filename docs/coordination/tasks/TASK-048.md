# TASK-048：建立 Person、權限、資格與 Event 的本機資料基礎

## 目標

依 TASK-047 核准的概念模型，一次建立可版本化、可離線驗證且尚未連接 production 行為的
local persistence foundation：Alembic migration、Docker PostgreSQL、SQLAlchemy models、domain/
repository 邊界、in-memory fixtures 與 PostgreSQL integration tests。成果必須證明 schema、
transaction、資格池發布快照、last-admin 防護、audit atomicity 與 backfill idempotency，而不連線
Supabase production、不部署、不改現有 Web Portal／LINE／排程服務的正式行為。

## 已核准產品模型

1. `people` 是自然人基本單位，直接保存：
   - `portal_access_level`：`basic`／`officer`／`admin`；
   - `portal_status`：`pending`／`active`／`disabled`／`inactive`／`blocked`。
2. `members` 保持永久正式校友名冊，與 Person 為可漸進回填的 0..1 關係；非 Member 不得被
   塞入校友名冊。
3. `auth_identities` 多對一連到 Person：同一 Person 可綁同 provider 多帳號；只有
   `(provider, provider_subject)` 全域唯一。Pending identity 可由 admin 匹配既有 Person/Member、
   建立非 Member Person或 blocked。
4. `person_qualifications` 是持久多值資格池，第一版包含 `team_player`、`guest_player`、
   `affiliate`、`staff`。Qualification 不授予 Portal 管理能力。
5. 非 Member 可成為 officer/admin；access level 不自動授予 `team_player`。Admin 第一版繼承
   officer capabilities。
6. Event 草稿定義 eligibility rules；發布 transaction 依當下 qualification 自動產生
   `event_invitees` 快照，另支援具 actor/reason audit 的 individual/manual include/exclude。
7. Attendance、roster 與統計必須區分 `team_player` 與 `guest_player`；guest 不得污染正式
   Member 名單或正式隊員統計。
8. Disabled 是暫停、inactive 是不活躍但保留歷史、blocked 是明確封鎖；未知值 fail closed。

## 使用者價值

- 未來新增聚餐、旅遊、交通、住宿、友誼賽或槍手，不需再次重做核心身分模型。
- 每屆校友名冊保持乾淨，親友與客座球員仍可安全登入與參與被允許的活動。
- 多個 LINE／Google／Apple identity 可歸屬同一 Person，支援未來 Flutter App。
- 正式 migration 前，先在隔離 PostgreSQL 反覆驗證 constraint、rollback 與 concurrency。

## 工作範圍

### A. Migration 與本機資料庫

1. 導入 Alembic 作為 repository 的版本化 migration 工具：
   - 工具依賴只能放在 development/migration 範圍，不加入各 Cloud Run runtime requirements。
   - 不使用 autogenerate 取代人工 review；migration 檔需明確、可讀且 Python 3.10 相容。
2. 提供 repository-local Docker Compose PostgreSQL：
   - 使用明顯 local-only 假帳密、固定非 production database 名稱與可清除 volume。
   - 不讀取 `envs/**/.env.yaml`、DSN secret 或主機既有 production 環境變數。
   - port 可由 local-only setting 覆寫，避免碰撞；文件說明啟動、驗證與停止方法。
3. 處理無既有 migration history 的 baseline：
   - 建立可審查的 legacy schema test fixture，只涵蓋本任務 FK/backfill 所需且由 repository
     models 確認的表／欄位。
   - Alembic baseline 與 expand revisions 分離；明確記錄未來 production 必須先 inventory／
     stamp，不能把 local legacy fixture 當作已批准 production DDL。
   - 從 local legacy fixture → stamp baseline → upgrade head 的流程必須可重跑。

### B. Expand schema 與 models

建立本機 expand migration 與相符 SQLAlchemy models，至少涵蓋：

- `people`
- `members.person_id` nullable unique FK（相容期不強制所有舊 Member 已回填）
- `auth_identities`
- `person_qualifications`
- `access_audit`
- `events`
- `activities`
- Event eligibility qualification rules
- `event_invitees` snapshot 與 manual include/exclude source
- `event_attendance_replies`
- `activity_attendance_replies`
- Event manager assignments／必要的 Event audit 邊界

設計要求：

- 使用 text + CHECK 或等價可演進 constraint，不使用難以 rollback 的 PostgreSQL enum。
- FK、unique、時間範圍、狀態組合與 identity link 狀態有資料庫層保護。
- 時間使用 timezone-aware PostgreSQL `timestamptz`；系統呈現仍以 Asia/Taipei。
- 不把 token、provider payload、cookie、LINE user profile 或 secret 放入 audit。
- model/table 命名延續 `ntubtob` schema 與現有 SQLAlchemy 2.0 風格；若現有多個 Base 阻礙
  migration metadata，只做最小可相容整理並搜尋所有 callers，不全面重寫既有 models。

### C. Domain 與 repository contract

1. 建立小型 repository protocol/API，使 domain service 不直接綁 Flask request 或 module-level DB。
2. 建立單一 in-memory implementation 與一組明顯虛構 fixtures，不逐 table mock。
3. 建立 PostgreSQL implementation 或足以驗證相同 contract 的 persistence adapter。
4. 同一組 contract tests 應可套用在 in-memory 與 PostgreSQL implementation，至少覆蓋：
   - Person、Member link 與 non-member；
   - 同 provider 多 identities 連到同 Person，provider+subject 不得重複；
   - access/status fail-closed；
   - 多 qualifications、有效期與撤銷；
   - affiliate admin 不自動具有 team_player；
   - guest player 不建立 Member。

### D. 安全 mutation 與 Event snapshot domain

建立可測試 domain service（本任務不接正式 route/UI）：

- admin 核可 pending identity：匹配既有 Person/Member、建立 non-member Person、或 block；
- access level/status 變更與 append-only audit 同 transaction；
- actor/target request-time reload、禁止自我提權，並防止移除最後一位 active admin；
- concurrent admin demotion 測試不得讓系統落到零 active admins；
- Event publish 依 qualification eligibility 在同 transaction 建立固定 invitee snapshot；
- publish 重試不得產生重複 invitees；資格後續改變不得暗改既有 snapshot；
- individual/manual include/exclude 必須保存來源、actor與受限 reason；
- attendance 與 roster contract 能分流 team/guest，不建立預填的空 reply rows。

### E. Backfill rehearsal

提供只針對 local fixture 的可重跑 backfill：

- 每個既有 Member 建立或重用唯一 Person link；
- 不由姓名、LINE display name 或其他弱資訊自動合併不同人；
- 既有有效 Member 取得 `team_player` qualification；
- 現有 admin allowlist 僅使用明顯 fake IDs 的測試輸入演練，絕不讀正式 env；
- 重跑不建立重複 Person、qualification、identity 或 audit；
- 產生筆數、orphan、collision 與待人工確認摘要，不輸出敏感資料。

### F. 文件與開發操作

- 在 root README 或專用 local persistence README 提供 Windows PowerShell 與 Unix-like 指令。
- 清楚標示哪些命令只啟動 local Docker、哪些會執行 migration；任何 production URL 必須 fail closed。
- 說明 local data／volume 如何安全移除，且不得使用 workspace root 或廣泛路徑作刪除目標。
- 更新角色、Event 與 access matrix 文件，使 schema 名稱與實作一致。

## 非目標

- 不連線、讀取或修改 Supabase production；不執行 production stamp、DDL、backfill 或驗證查詢。
- 不修改正式 Web Portal route、模板、LINE Login、session、現有 Member 配對或 production role
  resolution；新 persistence 不得被現行 request path 自動啟用。
- 不建立正式角色管理 UI、Event CRUD UI、Google/Apple OAuth 或 Flutter App。
- 不切換現有 Game／game attendance 的真實來源，不修改 crawler ownership 或通知格式。
- 不發送 LINE／Discord，不人工 invoke webhook、Cloud Run、Function 或 Scheduler。
- 不修改 Secret Manager、IAM、Cloud Build、Cloud Run scaling、production env 或正式 schema。
- 不 push、建立 PR、merge 或部署。

## 安全與相容限制

- 所有 integration DSN 必須以 local host／Docker network 與指定 local database fail closed；偵測到
  Supabase host、非 local host 或未知 DSN 時拒絕執行 destructive setup／migration tests。
- 測試資料只能使用明顯虛構姓名、identity subjects 與 IDs。
- 不在 import-time 啟動 Docker、連 DB 或執行 migration。
- 現有 services/functions 不得因新增 module 而改變 import side effects。
- Migration downgrade 只用於 local rehearsal；未來 production rollback 原則仍是保留 expand
  schema並回退相容 application，不以 drop tables 作緊急 rollback。
- 任何無法從 repository 確認的 legacy schema 細節需記為 production inventory blocker，不可猜測。

## 驗收條件

1. 一組明確命令可啟動隔離 PostgreSQL、建立 legacy fixture、stamp baseline、upgrade head、載入
   fake seed 並執行 integration suite。
2. Alembic revision history、models 與實際 PostgreSQL schema 一致；所有新增 constraint 有正反測試。
3. 同 Person 可綁兩個 LINE identities；同 `(provider, subject)` 不可屬於兩人。
4. Non-member affiliate/guest 可存在且可成 admin；其 qualification 與 access 完全獨立。
5. Member backfill 可安全重跑，不重複且不以姓名自動合併。
6. Concurrent last-admin mutation 無法產生零 active admins。
7. Access mutation 與 audit 要嘛同時成功，要嘛同時 rollback。
8. Event publish 產生穩定 invitee snapshot；重試無重複，資格變更不回寫歷史 snapshot。
9. Team/guest attendance 與 roster 可區分，guest 不進正式 Member 統計。
10. In-memory 與 PostgreSQL repository contract 一致，測試不呼叫任何外部 API。
11. 現有 Web Portal、shared library 直接受影響測試、compile、Python 3.10 grammar、migration
    upgrade/downgrade rehearsal 與 `git diff --check` 通過。
12. 沒有讀取 secret、連 production、通知、雲端修改、push、PR、merge 或部署。

## 建議驗證命令

Codex 應依實際建立的工具補齊精確指令，至少涵蓋：

```text
docker compose config
docker compose up -d <local-postgres-service>
alembic upgrade head
python -m unittest <domain-and-repository-suites> -v
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q apps/web_portal shared_lib/shared_module
git diff --check
git status --short
```

必須在結束前停止本任務啟動的 container；是否保留 named volume由 local README 說明，不得擅自
刪除不屬於本任務的 container/volume。

## 主要預期變更

- Alembic config／revision files
- Local-only Docker Compose／migration scripts
- Development-only migration requirements
- `shared_lib/shared_module/models/` 的新增 models 與最小 registry 調整
- 新 domain／repository modules及 tests
- Local fake fixtures／seed
- 相關 README 與 planning/access matrix
- `docs/coordination/reports/TASK-048-CODEX.md`

## 交付與 commit 規則

- 主要工程成果使用一個描述性 commit，例如：
  `feat(data): add local person and event persistence foundation`
- Report、HANDOFF 與必要 review 修正可合併在最少量的描述性 commit，不為每次狀態更新建立 commit。
- 完成後將 `HANDOFF.yaml` 更新為 `ready_for_review / work`。
- 不得 push、PR、merge 或 deployment。

## Base commit

`64f2dca`
