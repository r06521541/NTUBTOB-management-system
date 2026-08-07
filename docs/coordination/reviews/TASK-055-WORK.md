# TASK-055 Work 驗收

## 結論

`accepted`。Repository 已具備不含 remote connection／dump／restore／SQL／delete 能力的 local artifact
verifier、固定 manifest/checksum contract、logical-backup runbook 與 migration recovery gates。Work 在
isolated PostgreSQL 16.4 fake environment 完成實際 custom-format dump/list/restore rehearsal，並在修正
standard-header interoperability defect 後，以同一真實 fake archive listing 驗證 parser 通過。

此結論只代表工作包與 local recovery shape 可用；production backup 尚未建立，Phase A migration 仍
blocked。

## 查驗基準

- Branch：`codex/task055-logical-backup-readiness`
- Task base：`fd647c01da9d7cc968a28e0b7229e1993b92abe1`
- Work planning：`b5d6447cf42714c86b6986c5c25db1cf1f5eabf4`
- Initial implementation：`046c5e9cd1be7f6a603c89180db2c71908de9c49`
- Standard-header fix：`3da76e1`
- Codex handoff：`400d37d0c891eef9669fe62d85735e7918600b12`
- Working tree clean。

## Work code／boundary review

- CLI 只有 `preflight`、`create`、`verify`，輸入均為 absolute local artifact paths。
- Subprocess 只可執行 local `pg_restore --list`／`--version`，使用 argument list、restricted environment、
  captured output 與 timeout；錯誤不回顯 listing、environment 或 command details。
- 工具無 `pg_dump`、database connection、restore、SQL、network、delete 或 overwrite 介面。
- Repository/traversal/symlink/reparse/non-regular/empty/existing output、foreign schema、checksum／manifest
  drift、unsupported TOC/comment metadata 與 sensitive TOC injection 均 fail closed。
- Sidecars exclusive-create；manifest 欄位固定且不含 connection／identity metadata。

## Defect 與修正

第一次 Work real-listing review 發現 PostgreSQL 16.4 標準 comment
`Dumped from database version: 16.4` 會被舊版全域 sensitive regex 誤拒。Work 要求 changes；Codex 先加
regression fixture，再以固定 standard comment metadata allowlist 修正，並保留對每一條 non-comment TOC
line 的 sensitive scan、object parser 與 schema restriction。修正版以同一 real fake listing 實跑通過。

## Work 實際驗證

- Bundled Python 3.12：`python -m unittest tests.portal_data.test_logical_backup -v`
  - 13/13 passed。
- Bundled Python 3.12：`python -m compileall -q tools tests/portal_data`
  - passed。
- `git diff --check`
  - passed。
- Isolated PostgreSQL 16.4 fake rehearsal：
  - task-owned container：`ntubtob-task055-review`；完成後 stopped。
  - task-owned named volume：`ntubtob-task055-review-data`；retained，未刪除。
  - custom-format schema-scoped dump/list：passed。
  - restore 到第二個 isolated database：passed。
  - restored fake rows：`2`；next identity sequence：`3`。
  - RLS enabled `true`／forced `false`；constraints `2`。
  - 修正版 parser 對 real fake `pg_restore --list`：passed。

## 尚未完成證據

- 本機 `py -3.10` launcher 指向不存在的 Store runtime；Python 3.10 hosted evidence 待 PR CI。
- Bundled Black invocation 持續逾時，isort 未取得 Work 本機證據；待 PR CI。
- 未建立、檢視或驗證 production archive；未證明 production direct reachability、client/server version、
  encrypted destination、credential process、archive size 或 production restore fidelity。

## 安全聲明

- 未讀 `.env.yaml`、DSN、secret、host、project ref、role 或 Owner external file。
- 未連 Supabase／production DB，未執行 production dump、SQL、restore、migration 或 data handling。
- 未修改 schema、RLS、grant、role、backup/PITR、cloud resources 或 deployment。

## 下一個閘門

Owner 可先授權 push／PR，以 Python 3.10 CI 補足版本與格式證據。合併後仍不得 migration；Work 必須另行
提出精確 production logical-backup execution 工作包，包含 source commit、client version、maintenance
window、credential boundary、repository 外 encrypted destination 與 stop conditions，取得 Owner 明確批准
後才能執行一次 production `pg_dump`。
