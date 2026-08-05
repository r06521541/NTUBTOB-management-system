# TASK-032：Version Web Portal Session Cookie and Recover Stale Login State

狀態：`ready_for_codex`
優先級：P1 authentication reliability
規劃者：Work
執行者：Codex
Base commit：`15881c5b886fc87e92cf0e6aeb5b4dca9d1df9c4`

## 1. 任務目標

讓曾使用舊Session Secret或舊cookie設定的Web Portal使用者，不必手動進入瀏覽器設定清除網站資料即可重新完成LINE Login；同時明確固定production session cookie安全屬性，保留TASK-029的session-bound OAuth state與fail-closed邊界。

## 2. 已確認現象與根因邊界

- TASK-030將commit `15881c5...` 部署為`web-portal-00029-dsc`，repository／HTTP驗證通過。
- Owner在既有Chrome一般視窗看到`Invalid state parameter`，因此依工作包rollback至`web-portal-00027-fwf`。
- 相同production URL在Chrome／Edge無痕視窗可正常登入；清除一般Chrome的該網站cookie後也可正常登入。
- 因此LINE Channel、callback URL與同一瀏覽器回程可運作；問題收斂為既有cookie jar的stale／collision／migration狀態，不需要server-side跨瀏覽器transaction或database schema。
- Production目前100% traffic仍在Ready的`web-portal-00027-fwf`；新revision保留但不承接traffic。

## 3. 工作範圍

### 3.1 Cookie版本化與production安全屬性

- Web Portal使用專用、版本化cookie名稱，例如`ntubtob_web_session_v2`，不得再依賴Flask預設`session`名稱。
- 明確設定：
  - `SESSION_COOKIE_HTTPONLY=True`
  - `SESSION_COOKIE_SAMESITE="Lax"`
  - `SESSION_COOKIE_PATH="/"`
  - production／未明確標示development時`SESSION_COOKIE_SECURE=True`
- 只有`WEB_PORTAL_ENV=development`且既有demo雙gate成立時，local HTTP demo可使用`Secure=False`；production或環境缺失必須fail closed為Secure。
- 不設定寬泛`SESSION_COOKIE_DOMAIN`；保持host-only。
- 登入入口應以安全、範圍精確的方式淘汰同host/path既有Flask預設`session`cookie；不得讀取、log或回傳舊cookie內容，也不得刪除其他名稱cookie。

### 3.2 Invalid state恢復

- Invalid／expired／cross-session OAuth state仍回400，且必須在LINE token exchange、DB或通知前停止。
- 400頁面提供清楚的「清除本網站登入狀態並重新登入」操作；操作只清除Web Portal session／OAuth transaction並建立全新state，不得重用舊code或state。
- 不把驗證失敗細節、nonce、state、code、cookie或Secret顯示給使用者或寫入log。
- 避免自動redirect loop；使用者須明確點擊重試。
- 若使用GET重試會形成logout-CSRF，應採等價的安全設計（例如400 response直接清除失敗session，再由普通站內連結開始全新`/line/login`），並在report說明取捨。

### 3.3 相容性與文件

- 保留現有LINE Login、Member授權、return path與demo行為。
- README記錄cookie版本遷移會讓既有Web Portal登入失效一次，以及如何在local demo使用HTTP。
- 不修改LINE Developers Console、callback URL、Secret或runtime env schema。

## 4. 必要離線測試

- Production／環境缺失：cookie name、Secure、HttpOnly、SameSite、Path與host-only契約正確。
- Development demo：HTTP session仍可在test client持續，且兩個demo gate缺一不可。
- `/line/login` response淘汰的cookie只有精確legacy名稱／path，不洩漏value。
- Invalid state回400、清除失敗session並提供明確重試入口，且LINE HTTP／DB完全未呼叫。
- 重試建立新的nonce/state；舊code/state不會被接受或重用。
- 正常同一client callback與既有Member session行為保持通過。
- 不同client callback仍fail closed，不因恢復UI降低transaction binding。
- 所有既有Web Portal tests保持通過。

## 5. 非目標與禁止事項

- 不新增Supabase table、schema、migration、server-sidetransaction store或cache。
- 不實作transferable bearer state、跨瀏覽器登入或將nonce／PKCE verifier放入可轉移URL。
- 不讀取、修改或顯示Secret、production env、cookie值、LINE code/state或個資。
- 不呼叫LINE、production DB、Cloud Run、Cloud Build或HTTP；測試全部mock／離線。
- 不部署、不rollback、不修改IAM／Secret／LINE Console／callback／Scheduler。
- 不push、不建立PR或merge，除非Owner另行批准TASK-032 PR工作包。

## 6. 驗收條件與命令

```powershell
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q apps/web_portal
python tools/deploy_web_portal.py
git diff --check
git status --short
```

- Python 3.10相容。
- Cookie migration與恢復流程有成功／失敗回歸測試。
- Demo local HTTP不破壞，production cookie預設安全。
- 沒有外部呼叫、schema、Secret或deployment mutation。
- Codex report、PROJECT_STATE與HANDOFF依協作流程更新。

## 7. 部署後續

TASK-032 merge後，Work應以新的main commit重建TASK-030 exact deployment source；部署前再次確認rollback revision。真實驗證應先用一般視窗的既有cookie情境確認版本化遷移，再以乾淨cookie確認LINE Login。任何production execution仍需Owner另行精確批准。
