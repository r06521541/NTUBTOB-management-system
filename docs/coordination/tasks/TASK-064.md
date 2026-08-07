# TASK-064：修正 Phase A function fingerprint 的CRLF誤判

## 任務目標

修正TASK-062 post-check對`pg_proc.prosrc`原始換行做MD5造成的跨平台誤判，使完全相同的approved function body
無論由LF或Windows CRLF SQL文字建立，都產生相同fingerprint；維持其他catalog、RLS、grant與aggregate gates
不變。完成後只重跑新的production read-only post-check，不修改production schema/function/data。

## Production事件事實

- TASK-063 pre-check strict validator passed。
- Owner執行exact migration一次；post-check輸出51 metrics。
- Strict combined validator唯一finding為`03_catalog.append_only_function_matches=false`；其餘exact post metrics
  未報錯，pre/post legacy aggregate counts另經boolean-only比較一致。
- Work在localhost fake PostgreSQL以approved migration SQL的CRLF版本精確重現同一false結果；LF版本既有tests通過。
- 合理根因是`prosrc`保留SQL Editor貼入的CRLF，而不是function行為或schema漂移；正式接受前仍須用修正後fixed
  post-check重新取得production read-only證據。

## 工作範圍

1. Post-check只在計算approved append-only function fingerprint前，將CRLF正規化為LF；若需兼容孤立CR，必須
   明確測試且不得弱化body fingerprint。
2. 更新post-check sidecar checksum、strict artifact verifier、fixtures及必要runbook/evidence文件。
3. 新增真PostgreSQL regression：同一approved migration以LF與CRLF執行時function fingerprint皆true；實質
   function body mutation仍false。
4. 保證其餘50項metrics、pre-check SQL/checksum、migration SQL/checksum與combined validator contract不變。
5. 跑PostgreSQL 15／16、完整portal-data suite、Python 3.10／Black CI、compile/isort/diff checks。

## 非目標與安全限制

- 不修改migration SQL、Alembic revisions、models、function definition、triggers、RLS、grants或runtime services。
- 不讀Owner CSV／archive／credential／env，不連Supabase／production，不執行production SQL。
- 不執行DDL/DML、migration retry、downgrade、drop、restore、backfill、deployment、notification或cloud操作。
- PR merge不授權production post-check；merge後須固定新checksum並由Owner另行執行唯一read-only query。

## 驗收條件

- LF／CRLF建立的exact approved function均通過；body語意或文字實質漂移仍fail closed。
- Pre-check與migration canonical SHA-256完全不變。
- Post-check只有必要的normalization expression與sidecar checksum變化，其他gate不弱化。
- Local PostgreSQL 15／16與hosted Python 3.10／Black CI全部通過。
- Task-ownedcontainer/network清除，repository clean。

## Base commit

`a88f836fd0f8a1c7cad0af294e63b8e574729512`
