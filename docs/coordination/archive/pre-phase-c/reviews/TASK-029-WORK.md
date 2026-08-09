# TASK-029 Work 驗收報告

驗收時間：2026-08-06（Asia/Taipei）

## 結論

- 結果：`accepted`
- Branch：`codex/fix-line-login-state-continuity`
- Base：`196c2087a1bfdf816f16aafc267c7008aa376f41`
- 實作 commit：`0a96355af0df073b77ad5d1432a392fd3833dc96`
- 文件完成 commit：`77efd5950f8a35f771fc80f242042c936bd4f05d`
- 下一位角色：Owner（決定是否 push／PR；部署與真實登入驗證須另案批准）

## 驗收結果

第二輪實作已解除第一輪的 login-CSRF／session swapping 阻塞：OAuth state 雖具簽章與期限，callback 仍必須與登入起始 session 的 nonce 相符；不同瀏覽器 cookie store 會在 LINE、資料庫或通知副作用前回傳 400。return path、LINE response shape 與 HTTP failure 亦採 fail closed。

Owner 選定「callback 留在原 external browser」後，authorization request 新增 LINE 官方支援的 `disable_auto_login=true`。官方文件明確說明此參數會停用 auto login，改用同一瀏覽器可用的 SSO 或 email 登入；因此 repository 修正方向與產品決策一致，且未以可轉移 bearer state 換取跨瀏覽器登入。

## Work 實際驗證

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 55 tests in 0.677s — OK (skipped=2)

python -m compileall -q apps/web_portal
OK

ast.parse(..., feature_version=(3, 10))
OK

git diff --check 196c208..HEAD
OK

git status --short
clean
```

兩個 skip 是既有 Windows 環境缺少 Unix `make`／`sh` 的 deployment contract executable coverage，與 TASK-029 行為無關。

## 尚未驗證與風險

- 尚未部署，未以真實 Safari、Chrome 或 LINE in-app browser 驗證；離線測試不能證明手機 OS／LINE App handoff 行為。
- callback URL 與登入起始頁必須是同一 hostname，host-only session cookie 才能延續。Repository 未發現 custom domain 證據；若實際入口另有網域，部署前必須確認。
- 停用 auto login 會增加使用者登入步驟，這是保留 transaction binding 的已知 UX 取捨。
- 未讀 production log、Secret 或 LINE Developers Console，也未呼叫 LINE／DB、部署、push、PR 或 merge。

## 建議

接受 repository 變更。下一步若 Owner 批准，可建立 Draft PR 跑 Python 3.10 CI；production deployment 與受控真實裝置 smoke test應另立工作包，並保留 callback 400／登入回歸的 rollback 條件。
