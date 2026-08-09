# TASK-014 Work Review

結論：`accepted_as_rolled_back`
日期：2026-08-05
Reviewer：Work
Target commit：`974433168b86e5638adce779ed8eccced0542094`

## 驗收摘要

TASK-014依Owner精確批准執行。Build、deploy與control-plane檢查成功，但唯一一次authenticated production `GET /healthz`回傳HTTP 404，符合預先定義的rollback trigger。已將100% traffic切回`game-broadcast-service-00030-pgg`並驗證rollback完成，因此不接受新revision繼續服務production traffic。

## 查證證據

- 隔離source由target commit直接匯出；原working tree文件未進build context。
- Game broadcast tests：26/26通過。
- Compile check：通過。
- Shared library：由相同source重新build；target artifact SHA-256為`b8148abdd2006839c7a853fb2b71843c62576475e2bd6db2ef274273316f77ef`。
- Cloud Build：`fe74ab5d-7fa8-4ff1-8220-fa914b569f63`成功。
- New revision：`game-broadcast-service-00031-s65`，Ready；digest `sha256:bbf30a215b895a1fd2037dc30f23915e7656c1a1d810d15af93e04a26aad8b9f`。
- Deployment control-plane：private IAM、runtime identity、concurrency 80、timeout 300 seconds及Secret references未漂移；三個Scheduler jobs維持原target、POST method、Asia/Taipei schedule及Enabled狀態。
- Smoke：唯一一次authenticated `GET /healthz`回傳HTTP 404；未重試。
- Rollback：`game-broadcast-service-00030-pgg` Ready並承接100% traffic；digest `sha256:7301a529d18506f5f46832090421924cd7c40e2726233d0062fbc2ea1a4c8698`；service仍無public IAM binding。

另有一次Cloud Build `08d76d08-28bf-4e83-8ee8-a25ff904d5a6`因PowerShell substitutions未加引號而在Docker build前失敗；唯讀確認production仍為`00030-pgg` 100%後才修正命令重送。

## 安全邊界

- 未呼叫invitation、cancellation或reminder routes。
- 未讀application logs或Secret values。
- 未修改Secret、IAM或Scheduler。
- 未部署其他服務，未執行production data操作。
- 隔離source與temporary env已清理。

## 待處理

404的根因尚未確認。已確認source與local tests存在`/healthz`，但目前不能從既有證據判定是canonical Cloud Run URL／audience、routing layer或runtime route registration問題。後續應另立唯讀優先診斷任務；再次production request、traffic mutation或deploy仍需Owner明確批准。
