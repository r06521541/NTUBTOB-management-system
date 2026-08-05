# Game Broadcast Health Check Production Deployment Package

Status：`rolled_back`
Task：`TASK-014`
Target：production `game-broadcast-service`
Commit：`974433168b86e5638adce779ed8eccced0542094`

Expected outcome：新增private、side-effect-free `GET /healthz`，business routes與deployment contract不變。

Current rollback revision：`game-broadcast-service-00030-pgg`。
Current rollback digest：`sha256:7301a529d18506f5f46832090421924cd7c40e2726233d0062fbc2ea1a4c8698`。

Preflight：current revision ready／active、100% traffic；private IAM與runtime contract未退化；required Secret versions Enabled；三個Scheduler jobs維持既有target與Asia/Taipei schedule。

Owner已批准`docs/coordination/tasks/TASK-014.md`第10節的精確範圍。

## Execution result

- Result：`rolled_back`。
- Failed pre-build attempt：Cloud Build `08d76d08-28bf-4e83-8ee8-a25ff904d5a6`；CLI substitutions quoting錯誤，Docker build前失敗，沒有production mutation。
- Successful build／deploy：Cloud Build `fe74ab5d-7fa8-4ff1-8220-fa914b569f63`。
- New revision：`game-broadcast-service-00031-s65`。
- New digest：`sha256:bbf30a215b895a1fd2037dc30f23915e7656c1a1d810d15af93e04a26aad8b9f`。
- Control-plane：new revision Ready並曾承接100% traffic；service維持private；runtime identity、concurrency、timeout、Secret references及Scheduler contract未漂移。
- Smoke check：唯一一次authenticated `GET /healthz`回傳HTTP 404；未重試且未呼叫business routes。
- Rollback：已將100% traffic切回`game-broadcast-service-00030-pgg`；rollback revision Ready，digest為`sha256:7301a529d18506f5f46832090421924cd7c40e2726233d0062fbc2ea1a4c8698`。
- Current state：`00031-s65`仍是latest ready revision但為0% traffic；`00030-pgg`承接100% traffic。
- Intentionally not performed：application log讀取、POST routes人工invoke、其他服務部署、Secret／IAM／Scheduler修改、production data操作。
- Cleanup：隔離build source及temporary `.env.yaml`已移除。

## Follow-up

TASK-015已確認build source與deployed image均包含正確health route，且該次404在精確時間窗內沒有Cloud Run container request log；404發生於Cloud Run frontend／container之前。後續極窄Cloud Audit `HttpIngress` policy log查詢亦為0筆，沒有證據支持可記錄的policy denial。下一個最小證據是另行批准的單次canonical URL／Cloud Run proxy request；任何新production endpoint invocation或traffic mutation仍需Owner另行批准。
