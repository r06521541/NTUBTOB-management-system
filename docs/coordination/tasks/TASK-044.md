# TASK-044：保留LINE登入後的受保護頁面目的地

## 目標

針對Owner在production LINE App內實測發現的問題：從`/attendance`開始登入，成功後卻落到空白公開首頁`/`。建立可離線重現的完整登入導向契約，集中目的地解析，修正已證實的遺失路徑，並加入不含OAuth／個資的安全診斷。

## 已確認事實

- Production匿名`GET /attendance`回302至`/redirect-to-login?next=/attendance`。
- Production登入選擇頁的normal與browser fallback links都包含`next=/attendance`。
- Owner使用LINE App內建瀏覽器選擇normal LINE登入，登入成功後實際落到`/`；LINE App內不方便觀察callback URL。
- 現有`line_login`把safe return path放入signed OAuth state，callback理論上redirect該值；現有測試分段驗證state，但沒有從protected route開始的完整端到端契約。
- 不應讀取既有production callback request URLs或輸出query，因為可能包含authorization code與OAuth state。

## 工作範圍

1. 先建立會走完整鏈的離線回歸測試：
   - 匿名請求`/attendance`。
   - 解析登入選擇頁的normal LINE link。
   - 啟動`/line/login`並從LINE authorization redirect安全取得／驗證state，不顯示或記錄state值。
   - mock LINE token/profile與models，完成callback。
   - 最終response必須redirect至`/attendance`，後續會員request可render attendance且不落到`/`。
   - 另涵蓋`/account`與`/game-roster/<id>`等安全站內目的地，以及惡意／ambiguous目的地fail closed。
2. 集中登入目的地解析／分類：
   - protected-route redirect、login choice、normal／browser login、state load、invalid-state recovery與successful callback使用同一組安全規則。
   - signed state仍是跨LINE provider round-trip的權威來源；不得以未簽名query、Referer或User-Agent決定callback目的地。
   - 不降低nonce compare、state expiry、safe local path或session cookie安全性。
3. 若端到端測試能重現，修正最小根本原因；若無法在現有程式重現：
   - 不得假裝已修好或加入無依據redirect hack。
   - 加入最小安全診斷，僅記錄固定分類／事件，例如`login_callback_destination=attendance`、`account`、`roster`或`default`。
   - 不記錄完整URL、query、code、state、nonce、cookie、LINE user ID、member ID、display name或Secret。
   - 記錄失敗不得改變登入結果。
4. 更新README，說明return-path契約、診斷欄位與不應記錄的資料。

## 非目標

- 不讀取production callback logs或request URL。
- 不實作Google／Apple OAuth，不改LINE Console、callback URI、channel credentials或Secret。
- 不改session cookie名稱／屬性、Member配對、role policy、schema、model或資料。
- 不新增跨瀏覽器bearer token、User-Agent sniffing、`line://`deep link或自動OS判斷。
- 不修改其他apps/functions/shared_lib，不發通知、不連production DB。
- 不push、不建立PR、不merge、不部署；後續另由Owner批准。

## 安全與設計限制

- 先寫可重現測試再改production code。
- 所有測試mock HTTP、LINE與models；不可發外部請求。
- logging測試必須以sentinel code/state/user/member值確認輸出完全不含敏感值。
- 目的地分類必須是固定allowlisted label，不可從raw path拼接log內容。
- 保持Python 3.10相容與diff聚焦。

## 驗收條件

1. 完整離線鏈從`/attendance`開始，callback成功後精確回`/attendance`並可render會員頁。
2. 其他合法會員目的地依安全規則返回；external、scheme-relative、backslash、control、encoded ambiguous及重複參數fail closed。
3. Normal LINE App與browser fallback都使用fresh nonce／signed state且保留目的地。
4. 診斷只包含固定事件與目的地分類，測試證明不含OAuth、cookie、LINE或Member資料。
5. 現有state continuity、cookie、account/logout、role與Demo測試保持通過。
6. Web Portal完整測試、compile、Python 3.10 grammar與diff check通過。

## 驗證命令

```text
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q apps/web_portal
git diff --check
git status --short
```

## 主要相關檔案

- `apps/web_portal/app.py`
- `apps/web_portal/line_login.py`
- `apps/web_portal/admin_security.py`
- `apps/web_portal/tests/test_admin_security.py`
- `apps/web_portal/tests/test_line_login.py`
- `apps/web_portal/README.md`

## 交付

- 使用一個描述性主要commit，例如`fix(web-portal): preserve protected destination through LINE login`。
- report與handoff併入完成commit，避免純流程commit。
- 完成後設為`ready_for_review / work`；不得push、PR、merge或deployment。

## Base commit

`3da0bb0d895e59cc06c7c62f7b195d2de328434f`

## 後續候選

TASK-045：移除LINE webhook出席回覆後對不存在`/clear-cache/attendance`的過時且無timeout HTTP呼叫。

