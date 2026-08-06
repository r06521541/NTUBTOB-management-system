# TASK-047：設計可持久化的球隊角色與權限演進方案

## 目標

在不修改正式 schema、不連線 production DB 的前提下，將現有 Web Portal 的
`member`／`officer`／`admin` capability prototype 整理成可安全實作的 production
RBAC 規格，明確定義角色來源、授予與撤銷流程、資料可見性、migration、相容 rollout
與 rollback，作為下一階段 Supabase schema 變更與管理介面的核准依據。

## 已確認現況

- `apps/web_portal/role_policy.py` 已集中定義三種角色與 capabilities。
- Production 已配對會員預設解析為 `member`；`WEB_PORTAL_ADMIN_MEMBER_IDS` 是目前唯一
  高權限來源，命中者解析為 `admin`。
- Production 沒有可信的 `officer` 資料來源，也沒有正式角色指派 UI。
- Demo 已能展示 member／officer／admin 與幹部活動管理，但 Demo session 不是正式授權來源。
- SQLAlchemy models 位於 `shared_lib/shared_module/models/`，主要 schema 為 `ntubtob`；
  repository 目前沒有正式 migration framework。
- Owner 已確認第一版產品方向：一般隊員管理自己的出席；幹部以上管理活動；只有系統管理者
  可管理會員配對與角色。

## 使用者價值

- 幹部角色未來可由系統安全授予，不需靠姓名、LINE profile 或散落的硬編碼判斷。
- 一般隊員、幹部及系統管理者的資料與操作邊界可被測試與稽核。
- schema 變更前先確定相容與 rollback，避免一次 rollout 造成所有會員無法登入或權限提升。
- 為後續正式活動管理、友誼賽、聚餐、旅遊及複合 Event 建立授權基礎。

## 工作範圍

1. 查證 repository 現況：
   - 盤點 Member、LINE user、session identity、admin allowlist、role policy、route guards、
     Demo event routes 及相關測試。
   - 搜尋所有 capability callers，列出目前已實際使用與只有 prototype／預留的能力。
   - 不讀取 `envs/**/.env.yaml`，只可參考 example key 與程式中的名稱。
2. 完成 production 權限矩陣：
   - 對 anonymous、pending/unmatched、member、officer、admin、disabled/left（規劃狀態）列出
     頁面可見、讀取資料、mutation、通知及角色管理權限。
   - 明確區分 UI 顯示、route authorization、資料列／欄位可見性。
   - 找不到 repository 或 Owner 決策證據的項目標示為待確認，不自行補足。
3. 提出資料模型選項並作出建議：
   - 至少比較「Member 單一 role 欄位」與「獨立 member-role assignment table」。
   - 評估一人多角色、角色歷程、撤銷、停權、離隊、稽核、外鍵與未知值 fail-closed。
   - 說明為何建議方案適合目前規模與未來 Event 管理；避免不必要的企業級複雜度。
4. 撰寫 migration 工作包草案，但不得執行：
   - DDL 概念／檔案順序、預設值、constraint、index、回填與驗證查詢。
   - 舊版與新版服務共存順序，先讀取 fallback、再寫入／管理、最後移除 allowlist 的階段。
   - `WEB_PORTAL_ADMIN_MEMBER_IDS` 在 rollout 期間的相容優先序及退場條件。
   - rollback 應優先回到 application fallback；不得假設可直接刪欄位或丟棄角色資料。
5. 定義角色管理流程：
   - 只有具 `assign_roles` capability 的 admin 可授予／撤銷 officer。
   - 不允許管理者移除最後一位可用 admin，並規劃 bootstrap／break-glass 邊界。
   - mutation 必須有 CSRF、重新查詢 actor 身分、禁止自我提權，並提出最低限度 audit 記錄。
   - 本任務只寫規格與可離線驗證的契約，不建立 UI 或 route。
6. 將成果更新至 `docs/planning/ROLE_ACCESS_PROPOSAL.md`，另建立一份聚焦 schema／rollout
   的設計文件（建議 `docs/planning/ROLE_PERSISTENCE_PLAN.md`），並同步 access matrix。
7. 將後續拆成最小可驗收 implementation tasks，至少包含：
   - schema migration 與相容讀取；
   - admin 角色指派 API／UI；
   - production officer 活動管理接線；
   - audit 與資料可見性強化。

## 非目標

- 不修改 SQLAlchemy model、Supabase/PostgreSQL schema，不建立或執行 DDL/migration。
- 不連 production DB，不讀寫正式成員或角色資料。
- 不新增 officer/admin 環境變數或修改 Secret Manager、IAM、Cloud Run、Cloud Build、Scheduler。
- 不建立正式角色指派、核可帳號或 Event CRUD route/UI。
- 不發送 LINE／Discord 通知，不呼叫外部 API。
- 不改 LINE Login、session cookie、OAuth state 或既有正式 route 行為。
- 不 push、PR、merge 或部署。

## 設計原則

- Server-side capability check 是授權邊界；隱藏按鈕不構成安全控制。
- 角色來源必須是 repository 能描述、DB 能驗證的可信資料，不從顯示名稱或 LINE profile 推論。
- 未知角色、失效 assignment、畸形資料及 migration 中間狀態一律 fail closed。
- Application rollout 必須能與舊 schema／舊 revision 短期共存。
- 管理網站角色不得隱含授權部署、Secret、IAM 或不可逆 production 操作。
- 保持 Python 3.10 與現有 Flask/Jinja/SQLAlchemy 架構，不建議大型重寫。

## 驗收條件

1. 文件中的已確認事實均可追溯至實際 code、tests 或既有核准文件。
2. 權限矩陣涵蓋角色、帳號狀態、route/mutation、通知與敏感資料邊界。
3. 至少兩種資料模型方案有具體比較，並提出一個符合目前需求的推薦方案。
4. migration 草案包含 forward、backfill、dual-read/相容 rollout、驗證及 rollback。
5. admin allowlist 的過渡與退場策略清楚，且 rollout 不會讓既有 admin 突然失權。
6. 角色授予／撤銷、最後 admin、防自我提權、CSRF 與 audit 規則明確。
7. 待 Owner 決策事項集中列出，沒有把假設寫成已確認規則。
8. 未修改程式、schema、環境設定或正式資源；`git diff --check` 通過。

## 驗證命令

```text
git diff --check
git status --short
```

文件引用程式行為時，需以 `rg` 搜尋所有相關 callers 並記錄查證範圍。本任務沒有程式變更，
不要求重跑完整 Web Portal suite；若 Codex 為了驗證既有契約執行測試，須記錄實際結果。

## 主要相關檔案

- `apps/web_portal/role_policy.py`
- `apps/web_portal/admin_security.py`
- `apps/web_portal/app.py`
- `apps/web_portal/demo_portal.py`
- `apps/web_portal/demo_events.py`
- `apps/web_portal/tests/`
- `shared_lib/shared_module/models/`
- `docs/planning/ROLE_ACCESS_PROPOSAL.md`
- `docs/planning/WEB_PORTAL_ACCESS_MATRIX.md`
- 新增 `docs/planning/ROLE_PERSISTENCE_PLAN.md`

## 待 Owner 決策（由本任務提出證據與建議，不代替 Owner 決定）

- 普通隊員能看未回覆者姓名，或只能看統計人數。
- 幹部能否直接送出正式通知；建議與「準備通知」分離。
- 是否允許一人同時具有多個業務角色。
- 電話、醫療資訊、私人備註等敏感欄位的可見角色。
- admin 是否永遠繼承 officer 能力，以及 break-glass admin 的管理方式。

## 交付與交棒

- 主要成果應使用一個描述性 commit，例如：
  `docs(web-portal): design persistent team role rollout`
- 完成後建立 `docs/coordination/reports/TASK-047-CODEX.md`。
- 將 `HANDOFF.yaml` 更新為 `ready_for_review / work`。
- 不得 push、PR、merge、migration 或 deployment。

## Base commit

`602a8394c3dd47716da2d8b225743466516a304b`
