# TASK-030：Web Portal LINE Login Production Rollout and Controlled Smoke Test

狀態：`awaiting_owner_approval`  
優先級：P1 authentication correctness  
規劃／執行／驗收：Work  
Approved source candidate：`6765448ac64950cfe35008e637bc2c529954e106`

## 1. 任務目標

將已由 PR #39 squash merge、Python 3.10 CI 成功的 Web Portal LINE Login 修正部署至 production `web-portal`，再由 Owner 在原本發起登入的 external browser 完成一次受控登入，確認不再因 LINE App handoff 造成 `Invalid state parameter`。

本任務分為「部署」與「Owner 手動 smoke test」兩階段。部署成功不等於登入已驗證；Owner 未完成真實登入前不得宣稱問題已在線上解除。

## 2. 精確目標

- GCP project：`ntubtob-schedule-405614`
- Region：`asia-east1`
- Cloud Run service：`web-portal`
- Source／image tag：`6765448ac64950cfe35008e637bc2c529954e106`
- PR／CI：PR #39；Actions run `31033393383`，Python 3.10 success
- Expected URL：`https://web-portal-7uz453jt3a-de.a.run.app`
- Rollback candidate：`web-portal-00027-fwf`（TASK-027 最後確認的 healthy revision；執行前必須唯讀重查 Ready、image 與 traffic）
- LINE Login Secret ref：`web-portal-line-login-channel-secret:1`
- Session Secret ref：`web-portal-session-secret-key:1`
- Database Secret ref：沿用既有 `supabase-database-password:latest`

## 3. 已確認事實

- TASK-029 保留 session-bound OAuth state；跨 cookie store callback 會在 LINE／DB 前 fail closed。
- Authorization URL 新增 LINE 官方支援的 `disable_auto_login=true`，目標是停用 mobile external-browser auto login／App handoff，改由同一瀏覽器完成 SSO 或帳密登入。
- Work 本機驗證 Web Portal 55 tests 通過、2 個既有 Windows make/sh skips；compile、Python 3.10 grammar 與 diff check 通過。
- PR #39 已 merge；production 尚未包含此 commit。
- TASK-027 最後確認 `web-portal-00027-fwf` Ready 且承接 100% traffic；此狀態可能漂移，不能只靠舊文件直接部署。
- 真實 LINE Login 會呼叫 LINE token/profile API並查詢 production Member／LineUser，但本 smoke test不修改 Member、配對、schema 或其他 production data。

## 4. 部署前唯讀 preflight

執行前必須停止於 mutation 之前並確認：

1. 使用獨立 clean worktree checkout exact commit `6765448...`，不得重設或覆寫目前 diverged 的本機 `main`。
2. gcloud account、project與region符合 Owner 預期；不得輸出 access token。
3. `web-portal-00027-fwf` 仍為 Ready且可作 rollback；記錄目前 serving revision與traffic。
4. Service仍為 public，runtime identity未漂移。
5. 三個 runtime Secret references存在且版本 metadata可用；不得讀取 Secret payload。
6. Callback host仍為 `web-portal-7uz453jt3a-de.a.run.app`，且實際登入入口使用同一 hostname；若使用 custom domain立即停止。
7. Production未開啟 demo gates；temporary deployment env不存在。
8. 再執行 Web Portal與deployment wrapper離線測試、compile及dry-run。

任一項不符即停止並交回 Owner，不得自行修改 IAM、Secret、LINE Console、callback或runtime env修補。

## 5. 已規劃的部署命令

只有 Owner 批准第 10 節精確文字後，才可在 exact source worktree 執行：

```powershell
python tools/deploy_web_portal.py --execute `
  --approved-commit 6765448ac64950cfe35008e637bc2c529954e106 `
  --rollback-revision web-portal-00027-fwf `
  --line-login-secret-ref web-portal-line-login-channel-secret:1 `
  --session-secret-ref web-portal-session-secret-key:1
```

Wrapper 可 build、deploy、驗證 revision／digest／traffic／public boundary／runtime Secret classifications，並各呼叫一次無副作用 `GET /`（200）與 `GET /demo/`（404）。不得讀取 response body。

## 6. Owner 手動 LINE Login smoke test

部署與 wrapper 驗證成功後，由 Owner 使用原先發生問題的 external browser：

1. 關閉 local `127.0.0.1:8080` 分頁，開啟 production Web Portal hostname。
2. 在該 external browser開始 LINE Login；不得複製 callback URL到另一瀏覽器或無痕視窗。
3. 確認 LINE authorization畫面仍留在同一 browser context；允許 LINE 官方 SSO／email／QR UI。
4. 登入後確認 callback回到同一 hostname，且不出現 `Invalid state parameter`。
5. 只確認已登入頁面可讀；不得進入 Member配對、執行管理 POST、修改出席或通知偏好。
6. 不提供螢幕截圖中的個資、authorization code、state或cookie；Work只記錄成功／錯誤類型與時間。

如果 Owner的LINE帳號尚未與有效 Member配對，顯示等待核可頁不算 state失敗；但需記錄為「callback成功、Member授權未通過」。

## 7. Rollback 與停止條件

下列任一項成立，停止 smoke test並將 100% traffic rollback至預先確認仍 Ready的 `web-portal-00027-fwf`：

- 新 revision無法 Ready、traffic不是100%或image／revision無法對應批准 commit。
- Public boundary、runtime identity或Secret reference發生非預期漂移。
- `/` 非200、`/demo/` 非404，或production demo可存取。
- 新部署後登入仍在正常同一瀏覽器流程中穩定產生 `Invalid state parameter`，且排除使用localhost、不同hostname、無痕／跨瀏覽器等操作錯誤。
- 出現 Secret／authorization code／cookie洩漏、非預期DB寫入、通知或管理副作用。

Rollback只切traffic，不刪除revision／image、不修改Secret／IAM／LINE Console。若登入問題只在特定手機環境出現且Web Portal其他檢查正常，先停止並由Owner決定是否rollback，不自行擴張診斷。

## 8. 非目標與禁止事項

- 不修改 Secret值／版本、IAM、LINE Developers Console、callback URL或Cloud Run service設定。
- 不修改 schema、Member／LineUser資料、admin allowlist或任何 production data。
- 不發LINE／Discord通知，不測Member matching POST或其他寫入route。
- 不測 localhost完成真實callback；localhost與production host無法共享session cookie。
- 不部署其他服務，不刪除舊revision／image／branch。
- 不把真實登入憑證、state、code、cookie、個資或Secret寫入report。

## 9. 完成條件

- Exact commit部署成功，新revision Ready並承接100% traffic。
- Wrapper的control-plane、Secret metadata與兩個無副作用HTTP checks通過。
- Owner在external browser完成一次受控真實登入，結果分類清楚。
- 若失敗，依條件rollback或停止並留下不含敏感資訊的診斷摘要。
- 更新deployment report、PROJECT_STATE與HANDOFF；不得僅以測試通過宣稱線上登入已修復。

## 10. 待 Owner 精確批准文字

> 批准將 commit `6765448ac64950cfe35008e637bc2c529954e106` 部署至 production `web-portal`，依 TASK-030 與 deployment runbook 使用 Web Portal wrapper 執行 build、deploy、control-plane／Secret metadata驗證及各一次無副作用 `GET /` 與 `GET /demo/`；部署前須確認 `web-portal-00027-fwf` 仍為 Ready的rollback目標，符合TASK-030失敗條件時批准將100% traffic rollback至該revision。部署成功後，我批准由我本人在原external browser完成一次真實LINE Login smoke test，接受該測試會呼叫LINE token/profile API並唯讀查詢production Member／LineUser。不批准Secret payload讀取或修改、IAM／LINE Console／callback修改、管理POST、資料寫入、通知、其他服務部署、schema／data操作或刪除revision／image。
