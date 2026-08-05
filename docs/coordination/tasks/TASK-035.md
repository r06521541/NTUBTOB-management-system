# TASK-035：保護 Web Portal 比賽名單的會員隱私邊界

狀態：`awaiting_owner_approval`  
優先級：P1 security／privacy  
規劃角色：Work  
執行角色：Codex（Owner 核准後）  
Base commit：`198d3f0`

## 1. 目標

讓 production Web Portal 的比賽名單與未回覆姓名不再對未登入訪客公開。`/game-roster/<game_id>` 必須先確認目前 browser session 具有已完成 LINE Login 且已配對 Member 的最小身分，再查詢 Game、attendance 或 Member 資料。

本任務只建立「匿名訪客不得看隊員姓名」的第一層隱私邊界；普通隊員、幹部與系統管理者之間更細的姓名／未回覆名單可見規則，待 Owner 後續決策後另立 RBAC 任務。

## 2. 已確認現況

- `/game-roster/<int:game_id>` 目前沒有 authentication decorator，會查詢賽事與 attendance mapping，並輸出已回覆及未回覆成員姓名。
- `/attendance` 已有登入檢查，但使用 route 內的臨時判斷；`/match-member*` 使用獨立的 `admin_required`。
- LINE callback 只有在 `LineUser` 可配對到有效 `Member` 時才寫入 `user_id` 與 `member_id`。
- 現有正式角色 schema 尚未建立；`WEB_PORTAL_ADMIN_MEMBER_IDS` 只適用於系統管理操作，不適合拿來限制所有隊員名單。
- production Web Portal 已部署，本任務只修改 repository；任何 rollout 必須另行批准。

## 3. 實作範圍

### 3.1 可重用的會員 guard

- 在現有相鄰 security helper 中建立最小 `member_required`（或同等清楚命名）decorator。
- 未登入時安全 redirect 至現有 LINE Login 入口，並只保存站內 path 作為 return target。
- Session 必須同時有有效 `user_id` 與正整數 `member_id`；缺少、型別錯誤或布林值等不可信 session shape 必須 fail closed。
- Guard 不得因未登入 request 查詢 Game、Member、attendance、LINE 或其他外部服務。
- 不降低 `admin_required`；可在保持行為與測試相容下重用會員身分檢查，但不要做無關重構。

### 3.2 比賽名單保護

- 將 guard 套用於 `/game-roster/<int:game_id>`。
- 已登入且已配對 Member 的既有成功頁面內容先維持相容。
- 不在本任務決定普通隊員是否可看未回覆者姓名；登入會員仍維持目前資訊量，避免未經產品決策改變隊內操作。
- 補上不存在 game 的安全行為，避免 `None.id` 形成 500；採 repository 現有最一致的 404 行為，且不得查 attendance。
- Return URL 必須是相對站內 path，不得把 host、query 中的外部 URL 或不可信完整 request URL帶入 OAuth 流程。

### 3.3 離線測試與文件

- 新增 route/security tests，至少涵蓋：
  - 匿名 GET 被 redirect，且 Game／attendance／Member／HTTP 都未呼叫。
  - 只有 `user_id`、只有 `member_id`、錯誤型別及 bool member ID 均 fail closed。
  - 合法會員 session 可查看既有 roster 內容。
  - 找不到 game 回覆 404，且不查 attendance。
  - return target 僅為安全站內 path。
  - `admin_required` 既有 allowlist、CSRF 與 403 契約不退化。
- 更新 Web Portal README 或相關安全文件，明確記錄公開賽程與登入後名單的邊界；不要宣稱已完成正式 RBAC。
- 更新 Codex report、Work handoff 所需協作文件。

## 4. 非目標

- 不新增 role／capability 欄位，不修改 database schema 或建立 migration。
- 不實作普通隊員／幹部／系統管理者的完整 RBAC。
- 不改動 LINE Login provider、Channel Secret、callback URI、session cookie policy或管理者 allowlist內容。
- 不變更 attendance reply、通知、crawler、cache、Scheduler 或其他服務。
- 不讀取 `.env.yaml`、Secret payload或 production DB。
- 不部署、不呼叫 production、不發送 LINE／Discord 通知、不修改 Secret／IAM／Cloud Run。

## 5. 驗收條件

- 匿名使用者無法直接取得 roster 或未回覆者姓名。
- 未登入／無效 session 在任何資料查詢與外部副作用前 fail closed。
- 已登入且已配對 Member 仍可使用既有 roster 頁面。
- 無效 game ID 安全回覆 404，不形成 500。
- 既有 LINE Login、member matching 管理端點、CSRF 與 demo mode 行為不退化。
- 所有測試可在無 production DB、LINE、Discord 或外部 HTTP 下執行。

## 6. 驗證命令

```powershell
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q apps/web_portal
python tools/deploy_web_portal.py
git diff --check
git status --short
```

若 Windows 沒有全域 `python`，可使用工作區 bundled Python 或有效的 Python 3.10 launcher；兩項既有 `make`／`sh` platform skip 必須如實回報。

## 7. PR 工作包建議

Owner 若批准 TASK-035 與 PR 工作包，可允許 Codex 在 task branch 實作、建立描述性 commit、push、建立 Draft PR、查看 Python 3.10 CI，並由 Work 在同一 PR 驗收。仍不包含 merge、production deployment、Secret／IAM／DB／schema／data 操作或正式通知。
