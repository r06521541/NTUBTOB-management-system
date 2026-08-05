# TASK-029 Codex 實作報告

更新時間：2026-08-06T03:55:00+08:00

## 任務狀態

- 狀態：`blocked`（已完成安全補正，跨瀏覽器 continuity 需 Owner 產品／架構決策）
- branch：`codex/fix-line-login-state-continuity`
- base commit：`196c2087a1bfdf816f16aafc267c7008aa376f41`
- implementation commit：`c771961d2f777f9153a41ecef131d3623024c5cf`
- Work review commit：`4511383d1b0e8639b5c3db04c786cfec0a747dd9`
- security correction commit：`6966f6ac3b92be61334a1fc5b4adda36bb7ef7b6`
- push／PR／CI：未授權，未執行

## 實際修改

- 將 OAuth state 改為使用 Flask `SECRET_KEY`、專用 salt 與 timestamp 的 self-contained signed state，不再依賴起始瀏覽器的 session cookie。
- state 僅保存隨機 nonce 與已驗證的站內 return path，TTL 為 600 秒；缺少、過期、竄改或格式錯誤皆在 LINE／DB 呼叫前回應 400。
- callback 可在不同 Flask test client（模擬 LINE App 與外部瀏覽器切換）完成登入，並保留安全的站內返回位置。
- 外部、scheme-relative 與非絕對 return target 全部降級至站內預設頁，避免 open redirect。
- LINE token／profile requests 加入 10 秒 timeout、HTTP status 與 JSON／必要欄位檢查；失敗時回應不含 token、Secret 或上游 payload 的 502。
- 保留既有 LINE callback URI、member lookup、session identity 與未核可頁面行為；未修改 schema 或正式設定。
- README 補充跨瀏覽器 callback、安全邊界與離線測試限制。

## 修改檔案

- `apps/web_portal/app.py`
- `apps/web_portal/line_login.py`
- `apps/web_portal/tests/test_admin_security.py`
- `apps/web_portal/tests/test_line_login.py`
- `apps/web_portal/README.md`
- `docs/coordination/reports/TASK-029-CODEX.md`
- `docs/coordination/PROJECT_STATE.md`
- `docs/coordination/HANDOFF.yaml`

## 驗證命令與結果

使用 bundled CPython 3.12：

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 52 tests — OK (skipped=2)

python -m compileall -q apps/web_portal
通過

git diff --check
通過
```

兩個 skips 是 Windows 缺少 Unix `make`／`sh` 的既有 deployment contract；TASK-029 新增測試沒有 skip。Black／isort 未執行，因 bundled runtime 未安裝兩項工具；未下載依賴或修改環境。

## 安全與未執行事項

- 未呼叫真實 LINE endpoints、production DB、Secret Manager 或 production logs；所有 HTTP 與 models 均為 mock。
- 未讀取 `envs/**/.env.yaml`、Secret payload 或真實管理者 ID。
- 未部署、push、建立 PR、merge，未修改 schema、IAM、Secret、Scheduler 或 production data。
- 離線測試不能證明 LINE Developers callback 設定、production Secret、跨 App/browser 真實切換或 Supabase lookup 正確；需合併與部署另案批准後人工驗證。

## Work review 後安全補正

- Work 正確指出原 self-contained signed state 是可轉交 bearer：簽章只能防竄改，不能證明 callback 屬於發起登入的 browser transaction。
- callback 現在同時要求 signed state nonce 與發起瀏覽器 session nonce 以 constant-time comparison 相符；跨 session callback 在 LINE／DB 前回 400，不會建立登入 session。
- return path 額外拒絕反斜線、ASCII control characters，以及 encoded slash、backslash、control、percent 等模糊 separator。
- `access_token`、`userId` 必須為非空字串，`displayName` 必須為字串；無效 shape 回 502，且不執行後續 HTTP／DB。
- 補正後 54 項 Web Portal tests 通過，2 項既有 Windows make/sh tests 跳過；compile 與 diff check 通過。

## Blocking 與 Owner 可選方案

在 callback browser 不持有原 session cookie，且不新增共享一次性狀態或使用者確認步驟時，伺服器無法同時證明原始 browser transaction 並直接在另一瀏覽器建立登入 session。因此 TASK-029 的跨瀏覽器目標無法在目前範圍安全完成。

Owner 可另案選擇：

1. 優先盤點／調整 LINE Login 的 browser return 行為，使 callback 回到原本 external browser；維持現有 session-bound OAuth state，不新增儲存層。
2. 設計 two-phase login：callback 只把結果寫入 shared one-time transaction store，原始瀏覽器憑 session-bound secret claim 後才建立 session。需要選定具 TTL／atomic consume 的共享儲存、確認 UI、部署與 rollback 設計，但不一定需要修改正式 member schema。
3. 維持目前安全 fail-closed 行為，接受需要在 LINE 內建瀏覽器登入；不接受以 transferable signed bearer state 直接建立 session。

不建議接受 login-CSRF/session swapping 風險，也不建議把 PKCE verifier 放進可轉交 state；兩者都不能解決原始 browser transaction binding。
