# TASK-032 Work 驗收報告

驗收時間：2026-08-06（Asia/Taipei）

## 結論

- 結果：`accepted`
- Branch：`codex/version-web-session-cookie`
- Base：`15881c5b886fc87e92cf0e6aeb5b4dca9d1df9c4`
- 初版實作：`08ccd88d5aa2caa325d65c14be3bea7903224b84`
- 安全補正：`e2b769ade12c439acf1648671fe92ec11fc306a6`
- Codex completion：`9a7b4c8`
- 下一位角色：Owner（決定是否批准PR工作包）

## 驗收結果

- Session cookie改為專用版本化名稱`ntubtob_web_session_v2`，production／未明確環境採Secure、HttpOnly、SameSite=Lax、Path=/與host-only。
- 只有既有development demo雙gate同時成立時允許Secure=False，local HTTP demo保持可用。
- Legacy `session` cookie只在同host、Path=/精確到期，不讀取、輸出或記錄value，也不設定寬化Domain。
- Invalid／expired／cross-session OAuth state仍在LINE token/profile與DB前回400，錯誤頁只提供開始全新transaction的入口。
- 第一輪`session.clear()`可能造成logout-CSRF；第二輪已改為只清`oauth_state_nonce`與`next_url`。偽造callback不再登出既有user/member identity。
- Retry產生全新nonce/state，不重用舊code/state；跨client transaction binding保持fail closed。

## Work獨立驗證

```text
Web Portal tests: 58 passed, 2 existing Windows make/sh skips
compileall: passed
Python 3.10 grammar: passed
git diff --check 15881c5..HEAD: passed
working tree: clean
```

Codex另確認clean-worktree deployment dry-run通過且沒有cloud／HTTP；Work未執行`--execute`。

## 尚未驗證與風險

- 尚未在GitHub Python 3.10 hosted runner或真實瀏覽器／production驗證。
- Cookie名稱版本化會讓所有使用者重新登入一次，這是刻意migration行為。
- Repository無證據顯示舊cookie曾使用其他Domain／Path；即使存在，因新名稱不同也不會被應用讀取。
- 未push、PR、部署，未呼叫LINE／DB／Cloud Run，未修改schema、Secret、IAM或LINE Console。

## 建議

接受TASK-032。Owner若批准PR工作包，可push branch、建立Draft PR並查驗Python 3.10 CI；merge與production rollout仍須分別批准。部署時應以merge後的新exact main commit更新TASK-030，不直接恢復舊revision traffic。
