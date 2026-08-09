# TASK-057 Work review

## 驗收基準

- Branch：`codex/task057-isolated-restore-rehearsal`
- Implementation commit：`df03a462c9daf54e3ba398748f0bf669b146abbd`
- Reviewed HEAD：`633f1821d33b46ed7b2cde1bae546c57f06243db`
- Working tree：clean

## 已通過項目

- `preflight`／`execute` 分離，缺少 exact acknowledgement 時不呼叫 Docker。
- 固定 image ID、`--pull never`、`--network none`、無 published port、無 persistent volume／Docker socket。
- Database、socket、temp 使用 bounded tmpfs；archive parent 僅 read-only bind mount。
- Restore argv 固定，沒有 remote target／DSN／env-file／任意 SQL／destructive restore option passthrough。
- Catalog query 只回傳 13 個 boolean categories，不輸出 row values 或 exact row counts。
- 成功與主要失敗路徑均嘗試 cleanup，錯誤訊息不回顯 subprocess output。
- Work 重跑 Visual Studio Python 3.9 combined suites：29/29 passed。
- Work compile 與 `git diff --check`：passed。
- Work 唯讀 Docker 盤點：沒有 `ntubtob-task057-*` container，沒有 TASK-057 labeled volume。
- Codex 的 fake-data Docker rehearsal 證據與 report 一致；未發現 production archive／credential／remote 操作。

## Blocking finding

### Cleanup 必須驗證 task ownership 後才能刪除

`execute()` 在 `_start()` 前即設定 `may_need_cleanup = True`；若 `docker run` nonzero／timeout 或發生名稱競態，
`_cleanup()` 會對該名稱直接執行 `docker rm --force`。目前 cleanup 沒有先確認 container 同時具有
`com.ntubtob.task=TASK-057` label 與固定 image ID，因此理論上可能刪除在 inspect／start 間出現的同名非任務
container。隨機名稱使機率很低，但 destructive cleanup boundary 不可只依名稱推定 ownership。

必要補正：

- cleanup 前以固定、安全的 Docker inspect argv 取得且嚴格比對 task label與固定 image ID；
- ownership 不明、inspect 失敗或 mismatch 時不得 `rm`，必須 fail closed 並回報 sanitized cleanup/ownership
  category；
- 成功 start、start nonzero/timeout ambiguous、pre-existing container 與 foreign same-name race 都要有 tests；
- tests 必須證明 foreign/mismatched container 不會收到 `docker rm --force`；
- 不得放寬 image、network、mount、restore、catalog或 production-data boundary。

## 尚待證據

- 本機 Python 3.10 executable 不可用；Python 3.10 與 formatter 由修正後 PR CI 補足。
- Work 尚未重跑真實 fake-data Docker rehearsal；待 ownership 補正後再執行。

## 驗收結論

`changes_requested`。下一位角色：Codex。只需補正 cleanup ownership boundary 與對應測試／report。

本 review 未讀取、mount 或 restore production archive，未讀 credential env-file、未連 Supabase、未執行
production SQL／migration、未 push／PR／merge／部署。

## Cleanup ownership correction re-review

補正 commit `d91f19308dcb6bf0a4b672191d68860e28acd42b` 已解除 blocking finding：

- 每次 forced removal 前以固定 inspect argv 驗證 64-character immutable container ID、exact
  `com.ntubtob.task=TASK-057` label 與固定 image ID。
- Removal 改以經驗證的 immutable ID 為目標，不再依 generated name 刪除。
- Inspect timeout/nonzero/malformed、label/image mismatch 與 foreign same-name race 一律不呼叫 `rm --force`，
  並以 sanitized cleanup failure fail closed。
- Tests 覆蓋 successful start、ambiguous nonzero/timeout start、pre-existing container、foreign same-name、
  ownership mismatch與 immutable-ID removal。
- Work 重跑 combined suites：32/32 passed；compile、`git diff --check` passed；working tree clean。
- Work 唯讀 Docker 盤點再次確認沒有 TASK-057 container 或 labeled volume 殘留。

最終結論：`accepted`。尚待 PR 的 hosted Python 3.10 與 formatter evidence；該 PR／merge 不授權使用
production archive。下一位角色：Owner。
