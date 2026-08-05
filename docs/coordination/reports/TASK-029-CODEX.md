# TASK-029 Codex 實作報告

更新時間：2026-08-06T03:55:00+08:00

## 任務狀態

- 狀態：`ready_for_review`
- branch：`codex/fix-line-login-state-continuity`
- base commit：`196c2087a1bfdf816f16aafc267c7008aa376f41`
- implementation commit：`c771961d2f777f9153a41ecef131d3623024c5cf`
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
- 簽章 state 在 10 分鐘內可重送，但 LINE authorization code 為 callback 的交換憑據；本任務未加入跨 instance server-side nonce store，符合 TASK-029 不使用 process-local state store 的限制。
- 離線測試不能證明 LINE Developers callback 設定、production Secret、跨 App/browser 真實切換或 Supabase lookup 正確；需合併與部署另案批准後人工驗證。
