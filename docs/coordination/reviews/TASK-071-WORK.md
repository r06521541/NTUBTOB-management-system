# TASK-071 Work review

## 結論

`accepted`

驗收 commit：`e979cd61f6a2473bc819da3ea4304784b1f19935`

前次 blocking finding 已解除。Phase C production migration readiness package 現在能精確驗證新增 schema 定義，且本機 PostgreSQL 16 完整測試通過。此結論只接受 repository readiness package，不代表 production migration 已執行或已獲批准。

## 修正驗收

- post-check 現在 fingerprint 全部 19 個 Phase C-owned columns，包含 type、nullable、default、identity 與 generated 狀態。
- fingerprint 全部 15 個新增或修改的 constraints，包含 relation、名稱、constraint type、`pg_get_constraintdef` 與 validated 狀態。
- fingerprint 三個明確 indexes 的完整 `indexdef`。
- review tables 同時要求 RLS enabled、forced RLS 為零、policy 為零。
- strict verifier 會比對 SQL metric set 與 validator schema；即使竄改 SQL 並同步更新 checksum，也不能移除 required metric。
- PostgreSQL 負向測試證明錯誤 column default、同名錯誤 check constraint、同名同數量但定義錯誤的 index、forced RLS 與 policy 均會 fail closed。

## Work 獨立驗證

- `python -m tools.portal_data_phase_c_migration verify`：passed。
- `python -m tools.portal_data_phase_c_evidence verify`：passed。
- `python -m tools.portal_data_phase_c_readiness verify`：passed。
- `python -m compileall -q migrations tools tests/portal_data`：passed。
- 初始化 repository localhost-only PostgreSQL 16 fixture，stamp `0001` 並 upgrade 至 head：passed。
- `python -m unittest discover -s tests/portal_data -v`：155 tests passed。
- `git diff --check 501496b..e979cd6`：passed。

第一次完整測試在 PostgreSQL container 尚未 ready 時開始，因 startup/recovery 無法連線而失敗；確認 health 為 healthy 後，資料庫仍需依 repository 文件初始化 `ntubtob` fixture。完成初始化後，完整 155 項測試通過。這兩次是環境前置狀態，不是程式 assertion failure。

## 尚未執行與安全邊界

- 尚未取得 fresh production inventory，也未驗證 production revision、catalog、資料關係、權限或實際鎖定時間。
- 未連線 production Supabase、未執行 production migration、未部署、未開啟 runtime／identity-maintenance flags。
- 未發送 LINE／Discord 通知，未修改 Secret、IAM、Scheduler 或其他雲端資源。
- 後續若要執行 migration，仍須依 runbook 取得 fresh inventory、backup verification、exact commit／checksum 與 Owner 對該次 migration window 的明確批准。
