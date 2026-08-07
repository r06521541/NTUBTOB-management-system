# TASK-066：取得 Production Phase B 去識別化唯讀 inventory

## 任務目標

由Owner在Supabase SQL Editor執行一次已merge、checksum固定的Phase B唯讀inventory SQL，匯出唯一六欄CSV，
再由Work以repository validator離線驗證。此任務只取得正式環境當下的aggregate evidence，不執行backfill、
不產生executable mutation SQL，也不授權Phase B DML或Phase C。

## Exact source

- Approved repository commit：`8f40278bdbdabc0876ededba77264fa1016fd04b`
- SQL：`docs/operations/sql/TASK-065-phase-b-inventory.sql`
- SHA-256：`ee83a89a5b8e7548d78d3e26cbf3efc0c3d95f17fda067bb94be66afae45f9e5`
- Sidecar：`docs/operations/sql/TASK-065-phase-b-inventory.sql.sha256`
- Transaction：`BEGIN TRANSACTION READ ONLY`，local statement timeout 15秒、lock timeout 2秒、idle timeout 30秒，
  最後`ROLLBACK`。

不得修改、拆句、加入篩選、移除transaction boundary或以其他ad-hoc SQL代替。若Supabase顯示RLS提示、SQL錯誤、
timeout或結果欄位異常，停止並保留generic error category，不改寫後重試。

## 輸出契約

唯一結果必須是：

```text
section,metric,status,boolean_value,integer_value,text_value
```

內容只包含固定revision、boolean及aggregate counts；不得包含Member ID、姓名、LINE user ID、nickname、provider
subject、role identity、URL、credential或任何application row value。CSV保留在repository外，不commit、不貼完整
內容到公開PR／issue。

## Owner批准後的執行順序

1. Work確認main clean、HEAD與origin/main均為exact commit，SQL checksum及artifact verifier通過。
2. Owner在Supabase SQL Editor建立新query，從exact commit完整複製inventory SQL。
3. Owner核對第一句為`BEGIN TRANSACTION READ ONLY`、最後一句為`ROLLBACK`後執行一次。
4. Owner將唯一result匯出為repository外CSV並提供本機完整路徑給Work；不要手動編輯CSV。
5. Work只在本機執行：

   ```powershell
   python -m tools.portal_data_phase_b validate --kind inventory <CSV_PATH>
   ```

6. Work只回報fixed gates是否通過及aggregate counts；不得回報identity或Member row values。

## 必須通過的安全邊界

- transaction read-only為true，revision exactly `0003_legacy_bigint_activity_game`。
- 13張portal tables存在、13張RLS enabled、0 forced RLS、0 policies、2個append-only triggers。
- `members.person_id`尚未回填，People／identity／qualification／access audit及其他portal application rows均為0。
- duplicate LINE subject groups與orphan LINE→Member links均為0。
- Member及LINE各分類counts可形成後續deterministic backfill的approved aggregate input。

任一gate失敗即停止，不render mutation、不修production資料、不進入TASK-067。

## Freshness與凍結邊界

Inventory是時間點證據，不是永久保證。取得CSV後至未來Phase B execution完成前：

- 不進行Member配對、ignored狀態調整、LINE user維護或portal schema／RLS／policy／trigger變更；
- 一般game、attendance及通知服務可維持既有legacy行為，因本inventory不綁定其row counts；
- 若發生上述受控資料／schema變更、證據跨操作時段、或execution-time count gate漂移，必須停止並另案取得fresh
  inventory，不得放寬或重寫gate。

TASK-066成功後，Work才可建立TASK-067 exact Phase B execution package；TASK-067仍須Owner另行明確批准production
DML。僅完成TASK-066不表示backfill已獲准。

## 明確未授權

- 不執行或render `TASK-065-phase-b-backfill.sql`，不執行post-check。
- 不INSERT／UPDATE／DELETE／DDL、backfill、rollback、forward compensation或Phase C。
- 不讀env／Secret，不修改RLS policy、grant、role、IAM、Scheduler或cloud resources。
- 不部署，不發送LINE／Discord通知，不人工invoke任何服務。

## 成功條件

- Exact read-only SQL執行一次並正常ROLLBACK。
- Repository外CSV通過strict inventory validator。
- Work記錄sanitized aggregate結果、freshness boundary與下一步是否可建立TASK-067。
- 未發生任何production mutation或外部副作用。

## Owner批准文字

> 批准TASK-066：由我在Supabase SQL Editor依commit
> `8f40278bdbdabc0876ededba77264fa1016fd04b`執行一次SHA-256
> `ee83a89a5b8e7548d78d3e26cbf3efc0c3d95f17fda067bb94be66afae45f9e5`的
> `TASK-065-phase-b-inventory.sql`唯讀transaction，匯出唯一去識別六欄CSV供Work離線驗證。我接受從inventory
> 至後續execution前暫停Member配對、ignored／LINE user維護與portal schema／RLS／policy／trigger變更。
> 不批准mutation SQL render、backfill、post-check、DML／DDL、Phase C、deployment、Secret／IAM／Scheduler、
> notification或其他production操作；任一gate失敗或狀態漂移即停止。

## Base commit

`8f40278bdbdabc0876ededba77264fa1016fd04b`
