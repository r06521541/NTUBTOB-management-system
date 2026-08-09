# TASK-074 Work review

## 結論

`accepted`

- Branch：`codex/task-074-postgres15-phase-c-readiness`
- 實作 commit：`29854a5bcda321d16a046f44611a813b0615f26a`
- Draft PR：[PR #71](https://github.com/r06521541/NTUBTOB-management-system/pull/71)
- Repository：驗收前工作目錄乾淨；Work僅另加協作授權釐清與本review。

## 驗收結果

- Inventory與post-check現在只接受已審查的PostgreSQL major 15或16；14以下、17以上、false、缺值及畸形evidence皆fail closed。
- Verifier鎖定exact version expression，即使同步竄改checksum也不能放寬為`>= 15`。
- 19個Phase C columns、15個constraints、3個indexes的exact fingerprints，以及RLS／forced-RLS／zero-policy、Phase B與audit gates均未弱化。
- PostgreSQL 15.8與16.4使用相同fingerprints與完整failure rehearsals，沒有version-specific放寬。
- Inventory與post-check checksums已更新；migration artifact與checksum未變。TASK-073已使舊merged commit與舊CSV失效，避免誤執行。
- Compose仍預設16.4，但可用明確環境變數選15.8；hosted CI以matrix跑相同完整suite。

## Work獨立驗證

- PostgreSQL 15.8 localhost-only clean fixture／upgrade／完整suite：157/157 passed。
- PostgreSQL 16.4 localhost-only clean fixture／upgrade／完整suite：157/157 passed。
- `python -m tools.portal_data_phase_c_migration verify`：passed。
- `python -m tools.portal_data_phase_c_evidence verify`：passed。
- `python -m tools.portal_data_phase_c_readiness verify`：passed。
- `python -m compileall -q migrations tools tests/portal_data`：passed。
- `git diff --check`：passed。
- GitHub Actions run `31234515858`：PostgreSQL 15.8 job passed（1m08s）；PostgreSQL 16.4 job passed（1m11s）。
- Work驗收後已移除兩個task-owned localhost containers、networks與fake-data volumes。

## 協作限制釐清

Codex將「Owner明確授權」誤讀成每個新對話都需重複口頭批准，故在已commit／push後停止建立Draft PR。TASK-074與
`COLLABORATION.md`其實已包含standing Git／PR authorization。Work已修正`AGENTS.md`與`COLLABORATION.md`：

- repository記錄的standing authorization跨session有效；
- Codex原則上負責建立Draft PR；
- Work負責實際diff、hosted CI、ready與merge；
- production database、deployment、Secret及其他外部副作用仍須另行明確批准。

## 安全與後續

- 未連線production Supabase、未執行migration／DDL／DML、未部署或開啟runtime flags。
- 未修改Secret、IAM、Scheduler或發送LINE／Discord通知。
- TASK-074 merge後仍須以squash merged commit重新鎖定TASK-073，再取得新的30分鐘fresh inventory；先前CSV不可重用。
- 無blocking finding。依一般Git長期授權可在最終CI成功後squash merge。
