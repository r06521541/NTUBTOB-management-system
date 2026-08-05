# TASK-016 Codex Report

狀態：`ready_for_review`

## 實作結果

- `game-broadcast-service`與`notify-cronjob-service`不再於app import時建立`LineBotAnnouncementHelper`。
- 兩個service僅在第一次真正呼叫`announce(message)`時建立helper，之後於同一process重複使用，維持既有groups snapshot語意。
- `notify_cronjob_service` package import不再建立helper或傳送`Hi`。
- Health route、business route path／method、訊息內容、recipient selection與既有錯誤處理均未修改。
- 新增離線回歸測試，讓helper constructor在app／package import時 fail-on-call，並驗證lazy construction、message forwarding與per-process cache。

## Commit與PR

- Base：`974433168b86e5638adce779ed8eccced0542094`
- 文件：`6789d86` `docs(operations): record health rollout findings and startup-safety plan`
- 實作：`049a50e` `fix(scheduled-services): defer LINE helper startup side effects`
- Draft PR：[#32](https://github.com/r06521541/NTUBTOB-management-system/pull/32)

## 驗證

- Python 3.12.13 local：game broadcast `27/27`通過。
- Python 3.12.13 local：notify cron `8/8`通過。
- `python -m compileall -q apps/game_broadcast_service apps/notify_cronjob_service`：通過。
- `git diff --check`：通過。
- Python 3.10 GitHub Actions：run `30975661043`、job `92209003542`通過。

測試先以constructor fail-on-call重現兩個app的import-time初始化問題；notify package import測試亦會在舊版`__init__.py`直接建立helper時失敗。實作修正後，完整suites均通過。

## 安全與未驗證範圍

- 未部署、未呼叫production endpoint、未連production DB，也未發送LINE／Discord通知。
- 未讀取Secret或`.env.yaml`，未修改shared library、schema、Cloud Build、Docker、IAM、Scheduler或environment files。
- Lazy initialization將首次LINE group DB query延後至第一個announcement request；若當時DB不可用，既有例外與route處理語意維持不變。
- 尚待Work實際diff／commit驗收。
