# TASK-013 Codex Report

狀態：`ready_for_review`

## 實作結果

- `game-broadcast-service` 與 `notify-cronjob-service` 新增 private `GET /healthz`。
- Response 固定為 service name 與 `status: ok`，並設定 `Cache-Control: no-store`。
- Health route 位於各服務自己的 Blueprint，不讀取 DB，也不呼叫 LINE、Discord、crawler 或 weather。
- `POST /healthz` 保持 Flask 預設 `405 Method Not Allowed`。
- 既有 business routes、Cloud Run private flag、Secret bindings、Scheduler、shared library 與 schema 均未修改。
- 兩個 service README 與 deployment runbook 已說明 authenticated smoke check、限制及 production invocation 仍需明確授權。

## Commit 與 PR

- Base：`3389f96d6221f6ca0c566e6c74bf516012d83a83`
- 功能：`fa2390e` `feat(scheduled-services): add side-effect-free health checks`
- CI：`c7422e3` `ci(python): install Flask for route contract tests`
- Review fix：`a6273e8` `test(scheduled-services): exercise health checks through actual apps`
- Draft PR：[#30](https://github.com/r06521541/NTUBTOB-management-system/pull/30)

## 驗證

- Python 3.12.13 local：game broadcast `26/26` 通過。
- Python 3.12.13 local：notify cron `6/6` 通過。
- 各 service 的 `test_health.py` 單獨 discover：各 `2/2` 通過。
- `python -m compileall -q apps/game_broadcast_service apps/notify_cronjob_service`：通過。
- `git diff --check`：通過。
- GitHub Actions Python 3.10.20：最新 run `30964697592` 通過；job `92176031273`。

第一次 CI run `30964453832` 顯示 workflow 未安裝 Flask；route tests 因 `ModuleNotFoundError` 失敗。已在同一 PR 以最小步驟安裝 service 既有 pin `flask==3.0.0`，後續 run 通過。

Work 第一次 review 指出原測試只載入 standalone Blueprint，fail-on-call mocks 未接到 actual app。補正後測試以隔離的 `sys.modules` stubs 載入各 service 真實 `app.py`，連續對 actual test client 呼叫 health route，並驗證外部 dependency methods 未被呼叫、既有 business route path/method contract 不變。兩個 service 使用不同 module name，暫時 stubs 在載入後會還原。

## 安全與未驗證範圍

- 未部署、未呼叫 production 或 staging endpoint。
- 未讀取 Secret 或 `.env.yaml`，未修改 IAM、Scheduler、Secret、資料庫或通知設定。
- 未發送 LINE／Discord 通知，測試沒有網路或 production DB request。
- Health 200 僅證明 Flask process 與 route 可服務，不代表 DB、LINE、Discord、crawler 或 weather 健康。
- Production authenticated invocation 仍須納入特定部署授權，且應由具 Cloud Run Invoker 權限的身分執行。
