# TASK-063：執行 Production Phase A atomic schema expand

## 任務目標

在Owner一次性條件批准下，使用已merge且checksum固定的三份SQL，於Supabase production `ntubtob` schema
依序完成execution-time pre-check、單一transaction Phase A migration與post-check。任一gate失敗即停止；本任務
不包含Phase B backfill、Phase C application rollout或deployment。

## Exact source與SQL

- Approved repository commit：`871abd2bae8fefbe13f8ebc6cbd2f28baca1e56c`
- Pre-check：`docs/operations/sql/TASK-062-phase-a-precheck.sql`
  - SHA-256：`51ce7d88463f96bcf1a9cd12d0c3e1eeb5c17f5f0bdf19d466e7a0e296e6cd33`
- Migration：`docs/operations/sql/portal-data-0001-to-0003.sql`
  - SHA-256：`81fa1ba1a2d2d856d4b4393cbdfbc663d6c19759f758f36b08e76e39a964636a`
- Post-check：`docs/operations/sql/TASK-062-phase-a-postcheck.sql`
  - SHA-256：`4ed0c186db2df4c735d8dd93857d060efd48c57d2a05972cc90617c6b3c83546`
- Migration contract：exactly one transaction，transaction-local `lock_timeout = 5s`、
  `statement_timeout = 60s`，建立baseline marker後依序升至`0003_legacy_bigint_activity_game`。

Checksum以repository canonical verifier與adjacent sidecars為準；不得以Windows checkout的CRLF raw-byte hash取代
canonical artifact verification。不得修改、重排、拆句、加`IF NOT EXISTS`或手動stamp。

## Recovery artifact

- Exact retained set位於Owner既有repository外加密位置：
  - `portal-data-backup-20260807T063211Z.dump`
  - `portal-data-backup-20260807T063211Z.manifest.json`
  - `portal-data-backup-20260807T063211Z.sha256`
- Sanitized contract：56,903 bytes、archive SHA-256
  `a339a4ccd087a309468308e3912a08e5b661924447c93f57168d6e58b45f0f43`、PostgreSQL client major 16。
- TASK-058已證明此archive可在隔離PostgreSQL還原且catalog fidelity通過。
- Owner批准本TASK時，同時授權Work在migration window前對exact retained set執行一次既有Docker-backed read-only
  `verify`；不授權重跑dump、restore、修改／移動／刪除／上傳artifact或讀credential env-file。

## Maintenance boundary

- Window：Owner批准後，由第一次pre-check開始的30分鐘bounded window；若中斷、逾時或離開同一操作時段即失效。
- 從pre-check至post-check完成，凍結deployment、schema／RLS／grant／role維護、Member配對／管理操作、backfill
  與其他手動SQL。
- 不修改或暫停Scheduler／Cloud Run／Functions／IAM。一般服務保持legacy路徑。
- 為避免legacy aggregate count因正常回覆新增而漂移，選擇安靜時段並在約5分鐘執行區間避免引導隊員回覆；
  系統不強制封鎖使用者。若仍發生concurrent write，post-check會fail closed，schema不得因此downgrade。

## Owner一次性條件批准後的精確順序

### 0. Work local preflight

1. 確認`main`／`origin/main`與exact commit，working tree clean。
2. 執行migration artifact verifier及TASK-062 evidence artifact verifier。
3. 對exact retained backup set執行一次已批准read-only Docker-backed verify；確認checksum、manifest/listing與固定
   archive contract未漂移，且沒有task-ownedcontainer/network殘留。
4. 任一失敗即停止，不要求Owner執行SQL。

### 1. Owner production pre-check

1. 在Supabase SQL Editor開啟新的query，從exact commit完整複製pre-check SQL，不修改字元。
2. 執行一次，只匯出唯一six-column result為repository外CSV並交給Work。
3. Work執行strict `validate-pre`。任一metric、fingerprint、ownership／grant、marker、portal object或row contract
   不符即停止；不得修SQL重試或執行migration。

### 2. Owner production migration

只有Work在同一window明確回覆pre-check passed後：

1. 在新的Supabase SQL Editor query，從exact commit完整複製migration SQL。
2. 最後再核對檔名、canonical SHA-256及單一`BEGIN`／`COMMIT`。
3. 執行exactly once。不得人工重送個別statement。
4. 若明確error、lock／statement timeout或transaction rollback，停止並保留generic error category；不得直接重跑。

### 3. Owner production post-check

1. Migration顯示成功後立即在新的query執行exact post-check SQL一次。
2. 只匯出唯一six-column result為repository外CSV並交給Work。
3. Work使用strict combined validator比較pre/post。全部通過才宣告Phase A成功。

## Connection loss／狀態不明

- 不得假設成功或失敗，也不得重跑migration。
- 先執行exact post-check一次：若strict validation通過，視為已commit。
- 若post-check無法形成合法結果，再執行exact pre-check一次：若strict validation通過，證明仍為pre-state／已rollback。
- 若兩者皆不通過，停止、凍結Phase B/C並交回Owner做新recovery決策；不得downgrade、drop、stamp或清理物件。

## 成功條件

- Revision exactly `0003_legacy_bigint_activity_game`。
- 13張portal tables、97 columns、75 constraints、3 indexes、append-only function與2 triggers符合fingerprints。
- `members.person_id`為nullable bigint、unique／FK完整且non-null count 0。
- 13張new tables application row count 0；RLS 13 enabled、0 forced、0 policies。
- Portal PUBLIC／non-owner direct grants與non-owner default table ACL均為0。
- Legacy fingerprints、ownership／grant boundary與aggregate row counts在pre/post間不變。
- 現有runtime未接新schema；未部署、通知或修改Secret／IAM／Scheduler。

## Failure recovery

- Commit前錯誤：transaction應原子rollback；以approved read-only evidence確認pre-state後停止。
- Commit後post-check異常：保留expand-only schema，不執行destructive downgrade或drop；凍結Phase B/C並另案調查。
- Logical archive是資料災難recovery boundary，不因一般post-check finding直接restore；restore需要全新精確批准。

## 明確未授權

- Phase B Member／Person／identity backfill或任何application rows。
- Phase C runtime grants、RLS policies、Web／LINE／Scheduler接線或deployment。
- Secret／IAM／Scheduler／Cloud Run／Functions修改，真實LINE／Discord通知。
- 任意ad-hoc production query、interactive修補、單句retry、downgrade、drop、truncate、delete或restore。

## Owner批准文字

> 批准TASK-063：以commit `871abd2bae8fefbe13f8ebc6cbd2f28baca1e56c`為唯一source，依文件列出的
> pre-check、migration、post-check三份exact SQL與SHA-256，在pre-check與backup re-verification全部通過、
> 30分鐘window及freeze boundary成立時，執行一次production Phase A atomic schema expand。批准Work對既有exact
> retained backup set做一次read-only Docker-backed verify，並離線驗證Owner提供的pre/post CSV。任一stop
> condition或狀態不明即依TASK-063停止，不批准ad-hoc SQL、個別statement retry、downgrade／drop／restore、
> Phase B/C、deployment、Secret／IAM／Scheduler／notification或其他production data操作。

## Base commit

`871abd2bae8fefbe13f8ebc6cbd2f28baca1e56c`
