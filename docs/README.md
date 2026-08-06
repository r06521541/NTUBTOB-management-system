# 專案文件索引

本目錄依用途分成「協作與狀態」、「產品規劃」及「營運」三類。新工作應先從下列入口閱讀，不要依賴不存在的 `docs/STATUS.md` 或 `docs/ROADMAP.md`。

## 協作與目前狀態

- `coordination/HANDOFF.yaml`：目前任務、狀態與下一位角色的唯一真實來源。
- `coordination/PROJECT_STATE.md`：跨任務的系統現況、優先佇列、風險與已完成工作。
- `coordination/DECISIONS.md`：Owner 已核准的重要產品與技術決策。
- `coordination/COLLABORATION.md`：Work、Codex 與 Owner 的交棒、PR 及 commit 規則。
- `coordination/tasks/`：可執行任務規格。
- `coordination/reports/`：Codex 實作報告。
- `coordination/reviews/`：Work 驗收報告。

`tasks`、`reports` 與 `reviews` 是任務稽核歷史，不是 roadmap；判斷現在輪到誰一律以 `HANDOFF.yaml` 為準。

## 產品規劃

- `planning/WEB_PORTAL_PLAN.md`：Web Portal 產品方向與長期風險清單；部分早期事實已由後續任務解決，最新狀態以 `PROJECT_STATE.md` 為準。
- `planning/ROLE_ACCESS_PROPOSAL.md`：普通隊員、幹部與系統管理者的權限方向及未決議題。
- `planning/EVENT_MANAGEMENT_PLAN.md`：Event／Activity、多場比賽、旅遊與非聯盟活動願景。

規劃文件不自動授權 schema、migration、部署或正式環境操作。落地範圍必須另寫入當前 `TASK-xxx.md`。

## 營運與部署

- `operations/DEPLOYMENT_RUNBOOK.md`：production 部署批准閘門、停止條件與 rollback 原則。
- `operations/GEN2_FUNCTION_ROLLBACK.md`：Cloud Functions Gen2 recovery 流程。
- `operations/PRODUCTION_INVENTORY_2026-08-04.md`：特定日期的 production inventory 快照，不代表目前即時狀態。
- `operations/deployments/`：歷次部署證據與 rollback 基準。

部署文件記錄歷史證據；真正部署前仍須重新查證 exact commit、revision、traffic、identity 與 Secret reference metadata，並取得當次 Owner 授權。

## 維護規則

- 現況改變：更新 `PROJECT_STATE.md`。
- Owner 核准重要方向：更新 `DECISIONS.md`。
- 建立新工作：新增 `coordination/tasks/TASK-xxx.md` 並更新 `HANDOFF.yaml`。
- Codex 完成：新增 report；Work 驗收：新增 review。
- production deployment：新增 `operations/deployments/` 證據。
- 不為單純交棒狀態建立多個無描述性的 commit；遵循 `COLLABORATION.md` 的精簡規則。
