# TASK-068 Work 驗收

## 結論

`accepted`。Web Portal legacy identity maintenance guard預設關閉且server-side fail closed；去識別化drift
inventory與strict validator能容許正常pending／ignored candidates並拒絕cross-model、forced-RLS與audit關係漂移。
本任務尚未部署，production人工freeze仍有效。

## 實際查驗

- Implementation commits：`a6b8b10`、`a69ab20`；Work查驗base後實際diff、SQL、checksum、tests及report。
- 第一輪Work發現forced-RLS未檢查及audit gate可被`task065-*`非預期action／錯誤state繞過，退回修正。
- 第二輪確認`portal_rls_forced_count=0`及member／identity／qualification audits的action、deterministic request ID、
  actor、auth identity、target、before/after state均固定驗證。
- Web Portal：110 passed、2 skipped（Windows缺`make/sh`的既有平台條件）。
- Local PostgreSQL 16完整`tests/portal_data`：128/128 passed。
- Artifact verifier、compileall、`git diff --check`：passed。
- Local Docker container/network於驗收後移除，既有專用volume保留。
- PR #67 hosted job 92913165170：Python 3.10 setup、portal data formatting、PostgreSQL tests、Web Portal及所有
  required service suites全部success。

本機bundled Python 3.12／Black 26.3.1在無輸出狀態卡住，未修改檔案；hosted Python 3.10的`Check portal data
formatting`成功，故格式證據完整。此為local toolchain問題，不是產品失敗。

## 已確認行為

- `WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED`只有exact`true`可開啟；缺少、空白、case variant及未知值皆false。
- Guard關閉時，match／ignore POST在form parsing、ORM lookup/write與Discord前回固定503；admin/CSRF仍先驗證。
- Admin GET仍可唯讀查看pending rows，顯示maintenance notice並disabled controls；server-side guard不可由HTML繞過。
- Inventory為checksummed read-only transaction，只輸出固定六欄aggregate evidence。
- Pending與ignored counts為資訊；missing/wrong identity、qualification drift、duplicate/orphan、forced RLS及任何
  unexpected/inconsistent Phase B audit均fail closed。

## 尚未執行與風險

- Guard尚未部署；production match／ignore routes仍靠Owner人工freeze。
- 不得在production將guard設為true；true只恢復不安全的legacy single-write，並不代表dual-write完成。
- 未執行production drift inventory，未修改schema／RLS／Secret／IAM／Scheduler，未通知或部署。
- Ignored mapping、Person first-login activation、remap/unlink及transactional dual-write仍待後續任務。

## 下一步

先部署default-off guard以落實線上freeze，部署仍須Owner明確批准；之後另立TASK設計並實作transactional initial
match dual-write，且在其部署前不得啟用maintenance flag。
