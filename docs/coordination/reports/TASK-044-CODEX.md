# TASK-044 Codex 完工摘要

更新時間：2026-08-06（Asia/Taipei）

## 結果

- 狀態：`ready_for_review`
- Branch：`codex/deploy-pr49`
- Base commit：`3da0bb0d895e59cc06c7c62f7b195d2de328434f`
- Head：包含本報告的目前 commit
- 未 push、未建立 PR、未 merge、未部署。

## 實作與判斷

- 先新增從匿名 `/attendance`、登入選擇、LINE authorization signed state、mock callback到已登入 `/attendance` render 的完整離線回歸測試。
- 現有程式通過完整鏈，callback精確回到`/attendance`；`/account`與`/game-roster/23`亦保留目的地，因此本機無法重現Owner觀察到的production落到`/`。
- 依任務限制，未加入猜測性redirect修正。
- 成功callback現在只記錄固定診斷`line_login_callback destination=<category>`；category僅為`attendance`、`account`、`roster`或`default`。
- 測試以sentinel確認log不含完整return URL/query、authorization code、state、nonce、access token、cookie、LINE user ID、Member ID或display name。
- signed OAuth state、nonce continuity與原有safe local path仍決定實際redirect；診斷不參與控制流程。

## 驗證

```text
py -3.9 -m unittest discover -s apps/web_portal/tests -v
Ran 98 tests - OK (skipped=2)

py -3.9 -m compileall -q apps/web_portal
OK

Python 3.10 AST grammar
19 files - OK

git diff --check
OK
```

本機已安裝的Python 3.10 launcher指向不存在的WindowsApps executable，故實跑使用既有Python 3.9環境；另以AST `feature_version=(3, 10)`檢查語法。兩項skip是既有Windows缺少Unix `make`／`sh`的deployment contract tests。

## 邊界與後續

- 未讀production logs、未呼叫LINE、未連DB，所有HTTP與models均mock。
- 未修改schema、Secret、IAM、LINE Console、session安全規則或其他服務。
- 本次不宣稱production現象已修復；部署後需由Owner重做一次LINE App流程，再以固定category判斷callback當下目的地。
