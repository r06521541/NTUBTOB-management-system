# TASK-041：建立 Web Portal 角色與權限基礎層

## 目標

建立集中、可測試且 fail-closed 的 Web Portal authorization policy，讓普通隊員、幹部與系統管理者以 capability 表達權限，並把既有 production member/admin guards 接到同一套判斷。此階段不新增正式角色資料來源或資料庫欄位。

## 背景與已確認規則

- Production session 只保存有效 LINE `user_id` 與已配對 `member_id`。
- 所有有效登入且已配對的成員第一階段視為普通隊員。
- `WEB_PORTAL_ADMIN_MEMBER_IDS` 是目前唯一 production 高權限來源；其中成員視為系統管理者。
- Production 尚無可證明的幹部角色來源，因此第一階段不得從姓名、LINE profile、Member其他欄位或硬編碼名單推測幹部。
- Demo 已有 member／officer 行為與活動管理 prototype，可用來驗證不同角色的 UI 與 route 能力，但不得連接 production data。
- Owner 核准的第一版方向：成員管理自己的出席；幹部以上管理活動；只有系統管理者可做 Member 配對與未來角色指派。

## 使用者價值

- 後續正式活動管理可以直接依能力授權，不必在每個 route 重寫角色判斷。
- 一般隊員不會因 UI 隱藏不完整而取得管理操作。
- 系統管理者既有配對功能保持可用，並有集中測試防止權限退化。

## 工作範圍

1. 建立小型純 Python authorization policy module：
   - 明確角色：`member`、`officer`、`admin`。
   - 明確 capabilities，至少包含：`reply_own_attendance`、`manage_events`、`view_team_attendance`、`manage_members`、`assign_roles`。
   - role → capability mapping 必須集中、不可變且可單元測試。
   - 未知、缺失、型別錯誤的角色／member identity 一律無權限。
2. 建立 production principal resolution：
   - 有效 `user_id` 加正整數 `member_id` 才是 authenticated member。
   - admin allowlist 命中才提升為 `admin`。
   - production 不得產生 `officer`，直到未來有核准的正式資料來源。
3. 將既有 `member_required` 與 `admin_required` 接到集中 policy，保持 route 行為相容：
   - 匿名／畸形 session 在資料查詢前 redirect 或 403，沿用既有契約。
   - 非 admin 不得進入 `/match-member` 及其 POST actions。
   - CSRF 與既有 safe return path 不得改弱。
4. 整理 Demo role helper：
   - 避免 route authorization 與 template navigation 各自散落不同角色規則。
   - Demo 至少能在離線測試覆蓋 member、officer、admin 三角色的 capability 差異。
   - `admin` 可繼承第一版 officer capabilities；此繼承只屬產品 prototype，不授予 production officer 身分。
5. 新增 route access matrix 文件，列出現有 production 與 Demo routes 的 anonymous/member/officer/admin 存取規則、資料副作用與 guard；找不到證據的項目標示待確認，不憑空補足。
6. 更新 Web Portal README 說明目前 production role source、限制及未來 schema 邊界。

## 非目標

- 不修改 Supabase/PostgreSQL schema、SQLAlchemy models 或執行 migration／DDL。
- 不新增 `MEMBER_ROLE`、officer allowlist 或其他環境變數。
- 不建立角色指派、核可帳號、活動 CRUD 或通知 UI。
- 不把 Demo role/session 當成 production authorization source。
- 不修改 LINE Login、OAuth state、session cookie格式、Secret、IAM、Scheduler或deployment config。
- 不連 production DB、不發送 LINE／Discord、不部署、不push、不建立PR或merge。

## 設計限制

- Python 3.10相容，不新增dependency或大型framework。
- Policy應為無網路、無DB、無Flask request副作用的可測試核心；Flask decorator只做薄層解析與拒絕。
- UI隱藏不能取代server-side authorization。
- 既有合法member/admin路徑保持相容；未知狀態fail closed。
- 不順手全面重構`app.py`或其他服務。

## 驗收條件

1. 單一policy定義三個角色與capability，不在route/template重複建立不同mapping。
2. Production有效會員解析為member；只有既有admin allowlist命中者解析為admin；無production officer來源。
3. `member_required`／`admin_required`透過集中policy執行，現有成功與拒絕行為測試通過。
4. 非管理員在任何Member配對資料查詢或mutation前被拒絕；CSRF仍有效。
5. Demo member/officer/admin能力差異有離線測試，admin第一版包含officer能力。
6. 未知角色、畸形session、無效allowlist均fail closed。
7. Route access matrix與README與實際程式／測試一致。
8. 測試不呼叫外部HTTP、DB、通知或production服務。

## 驗證命令

```text
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q apps/web_portal
git diff --check
git status --short
```

另做Python 3.10 grammar檢查。Windows既有make/sh deployment tests可依原設計skip，但須清楚記錄；Hosted Python 3.10留待未來經Owner批准的PR工作包。

## 主要相關檔案

- `apps/web_portal/admin_security.py`
- `apps/web_portal/app.py`
- `apps/web_portal/demo_portal.py`
- `apps/web_portal/demo_events.py`
- `apps/web_portal/templates/demo/`
- `apps/web_portal/tests/`
- `apps/web_portal/README.md`
- `docs/planning/ROLE_ACCESS_PROPOSAL.md`
- 新 route access matrix 文件

## 已知風險與假設

- 集中既有decorator時可能改變redirect與403細節，必須以既有測試鎖住相容性。
- Demo目前主要使用officer角色；加入admin測試時不得讓production認證依賴Demo session。
- `view_team_attendance`的細部姓名可見規則尚未由Owner定案；TASK-041只定義capability，不擴張現有資料可見範圍。
- 幹部能否直接發送通知、核可帳號或查看敏感資料仍未決議，不應提前實作。

## 交付

- 主要實作使用描述性commit，例如：`refactor(web-portal): centralize role capability checks`。
- 完成後新增`docs/coordination/reports/TASK-041-CODEX.md`並將`HANDOFF.yaml`更新為`ready_for_review / work`。
- 本工作包只授權本機實作、測試、文件與commit。

## Base commit

`62d2de4`
