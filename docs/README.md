# 專案文件索引

本目錄依用途分成「協作與狀態」、「產品規劃」及「營運」三類。新工作應先從下列入口閱讀，不要依賴不存在的 `docs/STATUS.md` 或 `docs/ROADMAP.md`。

## 協作與目前狀態

- `coordination/HANDOFF.yaml`：目前任務、狀態與下一位角色的唯一真實來源。
- `coordination/PROJECT_STATE.md`：跨任務的系統現況、優先佇列、風險與已完成工作。
- `coordination/DECISIONS.md`：目前仍有效的產品、技術、授權與安全決策。
- `coordination/COLLABORATION.md`：Main Work、Domain Work、Codex writer、advisor 與 Owner 的角色、交棒、PR 及 commit 規則。
- `coordination/CODEX_SESSION_ANCHOR.md`：建立新 Codex writer session 時可直接貼上的固定啟動提示。
- `coordination/tasks/`：可執行任務規格。
- `coordination/reports/`：Codex writer 實作報告。
- `coordination/reviews/`：Main／Domain Work 驗收報告。
- `coordination/archive/`：已完成階段與舊 governance 歷史；預設不讀，先看 closeout／archive index。

`tasks`、`reports` 與 `reviews` 只放當前或尚未封存的工作；判斷現在輪到誰一律以 `HANDOFF.yaml` 為準。已完成
TASK-001～047 位於 `coordination/archive/pre-phase-c/`；Phase C 歷史證據位於 `coordination/archive/phase-c/`，
TASK-088～122 位於 `coordination/archive/mobile-foundation-2026-08/`，TASK-123～138與140／141位於
`coordination/archive/mobile-flutter-2026-08/`。日常只讀各目錄的closeout，不讀其中task/report/review全文。

## 產品規劃

- `planning/WEB_PORTAL_PLAN.md`：Web Portal 產品方向與長期風險清單；部分早期事實已由後續任務解決，最新狀態以 `PROJECT_STATE.md` 為準。
- `planning/ROLE_ACCESS_PROPOSAL.md`：普通隊員、幹部與系統管理者的權限方向及未決議題。
- `planning/EVENT_MANAGEMENT_PLAN.md`：Event／Activity、多場比賽、旅遊與非聯盟活動願景。
- `planning/FLUTTER_CLIENT_PLAN.md`：Flutter 第一階段產品、session、mobile API、通知與 staging 規格草案。
- `planning/MOBILE_AUTH_API_CONTRACT.md`：TASK-108 的 native LINE、App session、API v1、出席 enum 與 idempotency 契約。

規劃文件不自動授權 schema、migration、部署或正式環境操作。落地範圍必須另寫入當前 `TASK-xxx.md`。

## 營運與部署

- `operations/DEPLOYMENT_RUNBOOK.md`：production 部署批准閘門、停止條件與 rollback 原則。
- `operations/GEN2_FUNCTION_ROLLBACK.md`：Cloud Functions Gen2 recovery 流程。
- `operations/PRODUCTION_INVENTORY_2026-08-04.md`：特定日期的 production inventory 快照，不代表目前即時狀態。
- `operations/deployments/`：歷次部署證據與 rollback 基準。
- `operations/data/TASK-049-SUPABASE-CATALOG-SANITIZED.md`：TASK-049 去識別化的
  production schema catalog，供本機 migration fixture 與 review 使用；不含資料列或憑證。

## Release readiness

- `releases/MOBILE_RELEASE_MATRIX.md`：去識別化的 Android Closed Testing／公開版與 iOS
  TestFlight／公開版 gate matrix；區分 repository evidence 與未來 store、signing、真機、provider
  及 production Owner gate，不代表已上傳或可發布。

部署文件記錄歷史證據；真正部署前仍須重新查證 exact commit、revision、traffic、identity 與 Secret reference metadata，並取得當次 Owner 授權。

## 本機開發

- `development/AGENT_ENVIRONMENT.md`：Windows／Codex runtime、Git、Black、gcloud、Docker、psql、checksum 與
  中斷重試的已知陷阱；本機作業必讀。
- `development/LOCAL_PORTAL_DATA.md`：TASK-048 專用的隔離 PostgreSQL、Alembic migration rehearsal、contract tests 與 named-volume 清理方式；不授權或連接 production。

## 維護規則

- 現況改變：更新 `PROJECT_STATE.md`。
- Owner 核准重要方向：更新 `DECISIONS.md`。
- 建立新工作：新增 `coordination/tasks/TASK-xxx.md`，標記task type／delivery group／獨立PR需求，並更新
  `HANDOFF.yaml`。
- Codex 完成：更新該 TASK 唯一 report；Work 驗收：更新該 TASK 唯一 review。
- production deployment：新增 `operations/deployments/` 證據。
- 不為單純交棒狀態建立多個無描述性的 commit；TASK、push與PR不必一對一，遵循 `COLLABORATION.md` 的精簡規則。
- `COLLABORATION.md`、`PROJECT_STATE.md` 或未封存 tasks 超過文件預算時，先整理再建立 final PR；active decisions
  不設數量上限，但出現重複、衝突或閱讀困難時由 Work 整併與封存。
