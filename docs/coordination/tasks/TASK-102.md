# TASK-102 — Web Portal exact rollout-vector deployment contract

## 目標

修正 TASK-101 deployment 將 production Phase C active flag 重設為 repository default 的問題。每次 Web Portal
production execution 必須攜帶 Owner 核准的 exact rollout vector，並在 traffic promotion 前驗證新 revision。

## 核准向量來源

既有 Phase C activation evidence 對 `web-portal-00046-g8v` 記錄：

- `PORTAL_DATA_PHASE_C_ENABLED=true`
- `PORTAL_DATA_ROLLOUT_FREEZE_ENABLED=false`
- `WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED=false`

## 邊界

- rollout keys 從一般 source env 移除，再由 exact execution inputs 以 canonical YAML 重建。
- Cloud Build 驗證三個 inputs 僅為小寫 `true`／`false`，並與 temporary env 完全一致。
- revision contract 驗證三個 plain values；任一缺失、Secret-backed 或 drift 都在 promotion 前 fail closed。
- 不改 schema、資料、Secret、IAM 或其他服務；`web-portal-00046-g8v` 在修正重新獲准前維持 100%。

## 驗證

- deployment wrapper／Cloud Build contract tests。
- Web Portal full offline suite、compile、formatter、diff。
- hosted Python 3.10 CI與 final gate。
