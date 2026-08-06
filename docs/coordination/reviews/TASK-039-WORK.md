# TASK-039 Work 驗收報告

驗收時間：2026-08-06（Asia/Taipei）

## 結論

- 結果：`accepted_pending_hosted_ci`
- Branch：`codex/task-038-closeout`
- Base：`1c32d0a`
- Implementation：`dbdd287`
- Codex completion：`0025f7f`
- 下一步：依Owner完整工作包授權，建立Draft PR、查驗hosted Python 3.10 CI；通過後直接squash merge並執行受控Web Portal deployment。

## 驗收結果

- `/redirect-to-login`已移除meta refresh與JavaScript auto redirect，兩個登入方式都需要明確user action。
- Normal action使用`/line/login`且不含mode；browser fallback恰好使用`mode=browser`。
- Validated return path由server放入兩個`url_for`URL；normal／browser click各自建立fresh nonce與signed state，並保存相同safe internal target。
- 重複`next`在產生登入URL前回400；外部return target fail closed至首頁。
- Auth pages只使用本機CSS與logo，沒有外部Bootstrap、圖片、字型、script、UA sniffing或custom scheme。
- 375px CSS使用global border-box、100% panel寬度、mobile padding與至少52px操作目標，未見橫向溢位來源；focus-visible樣式存在。
- Error page維持TASK-038 fresh browser fallback；pending頁清楚區分已登入但尚未配對Member。

## Work獨立驗證

```text
Web Portal tests: 75 passed, 2 existing Windows make/sh skips
compileall apps/web_portal: passed
Web Portal deployment dry-run: passed; no cloud or HTTP
git diff --check 1c32d0a..HEAD: passed
working tree before review docs: clean
local runtime: bundled Python 3.12.13
```

## 尚未驗證與風險

- Hosted Python 3.10 CI尚待PR補證據。
- 尚未以實體375px browser做pixel-level visual QA；靜態CSS與response contract通過。
- 明確user gesture與fallback改善復原UX，但不能保證iOS／Android一定handoff至LINE App。
- Production smoke不得click兩個actions或跟隨LINE redirect；只能確認選擇頁200、無auto redirect及兩個same-site links存在。
- 尚未push、PR、merge或部署；未修改Secret、IAM、DB、schema、LINE Console或通知。

## Owner完整工作包

Owner授權Work從驗收到deployment完整執行。若hosted CI與PR狀態通過，可直接squash merge；merge後以exact main commit部署production `web-portal`，執行前重新唯讀鎖定當下100% traffic revision。Wrapper既有`GET /`、`GET /demo/`通過後，額外只做一次不點擊、不跟隨redirect的`GET /redirect-to-login?next=/future-games`，確認200、無meta／script auto redirect，normal與browser兩個same-site links存在。任一契約失敗時依批准條件rollback。
