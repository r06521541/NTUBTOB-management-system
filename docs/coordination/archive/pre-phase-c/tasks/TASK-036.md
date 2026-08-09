# TASK-036：部署 Web Portal 比賽名單會員隱私邊界

狀態：`completed`
優先級：P1 security rollout
規劃／執行角色：Work
Source commit：`5952e0b6d075ee2ba05c3b50057cc8108fc8e8cf`
Target：production Cloud Run `web-portal`（project `ntubtob-schedule-405614`、region `asia-east1`）

## 1. 目標

將已通過 PR #44 與 Python 3.10 CI 的 member-only roster guard 部署至 production，讓匿名或畸形 session 在任何 Game／attendance 查詢前無法取得 `/game-roster/<game_id>` 的隊員及未回覆者姓名。

本任務只 rollout 已合併的 immutable commit；不新增程式碼、不擴張 RBAC、不改 schema、Secret、IAM 或其他服務。

## 2. 已確認事實

- PR #44 已 squash merge，source commit 為 `5952e0b6d075ee2ba05c3b50057cc8108fc8e8cf`。
- Work 已驗收 61 項 Web Portal tests，GitHub Python 3.10 CI 成功。
- 上一次 Web Portal rollout 完成於 `web-portal-00032-f7z`，當時 Ready 且承接 100% traffic；這只是最近證據，執行前仍須重新唯讀確認目前 traffic，不可直接假設它仍是 rollback target。
- Deployment wrapper 會驗證 immutable image digest、new revision Ready、runtime contract、exact traffic promotion、IAM、`GET /` 與 `GET /demo/`，並可回復 exact approved revision。

## 3. Owner 核准前不得執行

- 不執行 wrapper `--execute`、Cloud Build、Cloud Run deploy 或 traffic mutation。
- 不呼叫 production HTTP、不查 production metadata／logs、不存取 DB。
- 不讀取 Secret payload，不修改 Secret、IAM、LINE、Scheduler 或 schema。

## 4. 核准後的精確執行流程

### 4.1 唯讀 preflight

1. 確認 active gcloud account、project `ntubtob-schedule-405614` 與 region `asia-east1`。
2. 確認 local source 為 clean、exact commit `5952e0b...`，且 deployment dry-run 通過。
3. 唯讀取得 `web-portal` 當下 100% traffic revision，確認 Ready，並將它鎖定為本次 exact rollback revision；若不是單一 100% revision、不是 Ready 或與已知邊界不一致，停止並回報 Owner。
4. 確認 service public invoker、runtime identity及兩個既有 Secret version references未漂移；只查 metadata／state，不讀取 Secret payload。
5. 確認 `web-portal-line-login-channel-secret:1` 與 `web-portal-session-secret-key:1` 仍為 enabled。
6. 確認 `apps/web_portal/.env.yaml` 不存在；不得輸出本機正式 env 的內容。

### 4.2 Build、deploy 與 wrapper 驗證

使用 `tools/deploy_web_portal.py --execute`，精確帶入：

- approved commit：`5952e0b6d075ee2ba05c3b50057cc8108fc8e8cf`
- preflight 鎖定的 exact rollback revision
- LINE Login Secret ref：`web-portal-line-login-channel-secret:1`
- Session Secret ref：`web-portal-session-secret-key:1`

Wrapper 必須先驗證 distinct new revision Ready 與 runtime contract，再 explicit promote exact new revision至100%，確認 traffic convergence後才做 IAM與HTTP checks。外層 command timeout必須長於wrapper bounded timeout。

### 4.3 額外隱私 smoke check

Wrapper成功後，只額外執行一次不跟隨redirect、不中繼cookie、無副作用的：

```text
GET /game-roster/1
```

預期 HTTP 302，`Location` 只能指向同站 `/redirect-to-login`，其 `next` 只能是 `/game-roster/1`。不得跟隨至 LINE Login，不得提供真實 OAuth code/state，不得測登入後 roster，也不得連 production DB。

## 5. 成功條件

- Cloud Build成功，new revision Ready且image tag／digest對應 exact source commit。
- New revision承接100% traffic；runtime identity、Secret references、public IAM與production demo gate未漂移。
- `GET /` 為200，`GET /demo/` 為404。
- 匿名 `GET /game-roster/1` 為安全302，Location符合上述站內登入邊界。
- Temporary env已清理，working tree沒有意外 credential file。

## 6. Rollback／停止條件

下列任一情況，若 traffic 已開始切換，將100% traffic回復至 preflight 鎖定的 exact舊revision；若尚未切換則保留舊traffic，不做多餘mutation：

- Build、revision readiness、digest或runtime contract失敗。
- Traffic promotion／convergence失敗。
- IAM、`GET /`、`GET /demo/` 或匿名 roster 302 contract失敗。
- Temporary env無法安全清理。

Rollback後只做唯讀確認舊revision Ready並承接100% traffic；不刪除新revision/image，不修改Secret/IAM，不人工invoke LINE Login或資料庫路徑。

## 7. 明確排除

- 不發送 LINE／Discord 通知。
- 不讀寫 production DB、不測登入後 roster、不操作 member matching。
- 不修改 Secret／IAM／Scheduler／callback設定或LINE Console。
- 不部署其他 app/function，不修改 schema／migration／data。
- 不刪除 revision、image、build或log。

## 8. Owner 決策

Owner 已批准將 source commit `5952e0b6d075ee2ba05c3b50057cc8108fc8e8cf` 部署至 production `web-portal`，允許上述 build、deploy、唯讀驗證、三個限定 HTTP checks，以及在失敗條件下 rollback 至執行前重新確認的 exact 100% traffic revision。

## 9. 執行結果

- 執行前 rollback target：`web-portal-00032-f7z`，Ready且承接100% traffic。
- Cloud Build ID：`d2e37557-2d53-418a-b1be-bd0e8458cf88`。
- 新 revision：`web-portal-00033-kzq`，Ready且承接100% traffic。
- Image digest：`sha256:31da45d6be0e9db367ea7c5353837b03c81f672c997aef66c9ef8a438a07197e`。
- `GET /`：200；`GET /demo/`：404。
- 匿名 `GET /game-roster/1`：302，Location為同站`/redirect-to-login?next=/game-roster/1`；未跟隨redirect。
- Temporary env已清理；未觸發rollback。
- 未修改Secret、IAM、DB、schema、data、LINE或其他服務。
