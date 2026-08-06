# TASK-044 Work 驗收

- 日期：2026-08-06（Asia/Taipei）
- Branch：`codex/deploy-pr49`
- 主要commit：`7ceed557200b9e566794f430113316c457b9d568`
- 診斷韌性修正：`c91d01752569480abea4edbb1609bd76847390d2`
- 結論：`accepted`

## 查驗結論

- 完整離線鏈從匿名`/attendance`經登入選擇、normal LINE authorization signed state、mock callback，到已登入`/attendance` render均成功；現有程式無法重現production落到`/`。
- `/account`與`/game-roster/<id>`的safe return path亦能存活於signed state round-trip；惡意與ambiguous inputs仍fail closed。
- 因無法重現根因，實作沒有加入強制跳轉、User-Agent判斷或其他猜測性workaround。
- 新診斷只輸出`attendance`、`account`、`roster`或`default`固定分類；sentinel測試確認不含URL/query、code、state、nonce、token、cookie、LINE／Member資料或Secret。
- Work第一輪發現logging handler故障可能讓成功callback變500；`c91d017`已改為best-effort邊界，fault-injection測試證明登入session與302目的地不受影響。

## Work獨立驗證

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 99 tests - OK (skipped=2)

python -m compileall -q apps/web_portal
OK

git diff --check
OK

git status --short
clean
```

兩項skip為既有Windows缺少Unix`make/sh`的deployment contract tests。Codex另回報19個Python檔案的Python 3.10 grammar check通過。

## 尚未解除事項

- 本任務沒有證明production現象已修復；只有部署這個安全診斷後，由Owner在LINE App重做流程，才可從固定category確認callback選擇。
- 若category為`attendance`但使用者仍落到`/`，下一步應檢查callback之後的瀏覽器／request鏈；若為`default`，再針對return-path進入signed state前的實際production路徑調查。
- 未push、PR、merge、部署或讀取production callback logs。

