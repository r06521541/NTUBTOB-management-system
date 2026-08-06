# TASK-038 Work 驗收報告

驗收時間：2026-08-06（Asia/Taipei）

## 結論

- 結果：`accepted_pending_hosted_ci`
- Branch：`codex/task-038-line-auto-login`
- Base：`b23bbec`
- Implementation：`0e7be34`
- Codex completion：`a5aa204`
- 下一步：依Owner完整工作包授權，建立Draft PR、查驗hosted Python 3.10 CI；通過後直接squash merge並執行受控Web Portal deployment。

## 驗收結果

- Normal `/line/login` authorization query不再包含`disable_auto_login`，恢復LINE auto-login eligibility。
- 只有allowlisted `mode=browser`加入`disable_auto_login=true`；未知、重複或衝突mode，以及重複`next`均在LINE redirect前回400。
- Normal與fallback每次建立fresh nonce與signed state；callback仍做constant-time session nonce compare。
- Signed-valid nonce mismatch只將已驗證safe internal return path放入錯誤頁fallback；tampered／missing／expired state使用固定`/attendance`。
- 錯誤頁fallback建立全新transaction，不重用舊authorization code、state或nonce。
- 沒有User-Agent sniffing、跨browser bearer state或cookie／OAuth安全邊界降級。
- TASK-037 minimal identity session、cookie policy、CSRF、admin、roster與demo suites均維持通過。

## Work獨立驗證

```text
Web Portal tests: 71 passed, 2 existing Windows make/sh skips
compileall apps/web_portal: passed
Web Portal deployment dry-run: passed; no cloud or HTTP
git diff --check b23bbec..HEAD: passed
working tree before review docs: clean
local runtime: bundled Python 3.12.13
```

## 尚未驗證與風險

- Hosted Python 3.10 CI尚待PR補證據。
- 離線authorization URL contract不能證明LINE in-app、Safari或Chrome實際auto-login UX；部署後仍須Owner人工操作。
- Normal auto-login若跨browser cookie context，仍會安全回400；新的browser fallback才是recover path，並不允許跨browser完成原transaction。
- Production smoke test不得跟隨至LINE authorization endpoint，不得使用真實code/state或登入DB頁面。
- 尚未push、PR、merge或部署；未修改Secret、IAM、DB、schema、LINE Console或通知。

## Owner完整工作包

Owner已授權Work完成驗收後的一連串PR、CI、merge與deployment。若hosted CI及PR狀態通過，可直接squash merge；merge後以exact main commit部署production `web-portal`，執行前重新唯讀鎖定當下100% traffic revision為rollback target。只允許wrapper既有`GET /`、`GET /demo/`及額外不跟隨redirect的`GET /line/login` contract check；不跟隨LINE URL、不做真實登入、不連production DB。任一build、revision、runtime contract、traffic、IAM或HTTP契約失敗時依wrapper規則rollback。
