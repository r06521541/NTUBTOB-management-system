# TASK-008 Work Deployment Verification

日期：2026-08-04
結論：`deployed_successfully`
下一位角色：Owner

## 核准與範圍

Owner 明確批准將 commit `086d663831cf49ddaa5f8413edd8508d1f6bf596` 部署至 production `game-broadcast-service`，並批准在定義失敗條件下將 traffic rollback 至 `game-broadcast-service-00029-vmc`。授權不包含人工 invoke、其他服務、Secret/IAM/Scheduler 修改或 production data 操作。

## Preflight

- Approved commit 與執行 HEAD 的完整 tree hash 相同：`63736bc4fb5aef2a53437ab52a114bcee102b2d6`。
- `apps/game_broadcast_service`、`shared_lib`、`makes` 與相關 env scope 相對 approved commit 無差異。
- Python 3.10 game broadcast tests：24/24 `OK`。
- GitHub Actions run `30922220358`：`success`。
- Current revision／rollback target、project、runtime identity、private boundary、Secret enabled states 與 Scheduler window 均於部署前重新確認。

## Deployment evidence

- Build ID：`80b086fc-f0c1-4f6b-a4e6-3acb456a1d6b`，`SUCCESS`。
- New revision：`game-broadcast-service-00030-pgg`。
- New digest：`sha256:7301a529d18506f5f46832090421924cd7c40e2726233d0062fbc2ea1a4c8698`。
- Revision conditions：Ready、Active、ContainerHealthy、ContainerReady 均為 `True`。
- Traffic：100% 至 `00030-pgg`。
- Runtime identity：未變。
- Secret references：database password latest、Weather API key 2、LINE token 1。
- IAM：沒有 `allUsers` Run invoker binding，維持 private。
- Scheduler：三個 jobs 維持 enabled，schedule 與 target 未修改。
- Temporary `apps/game_broadcast_service/.env.yaml`：已清理。

## 副作用與限制

- 沒有人工呼叫 invitation、cancellation 或 reminder endpoint。
- 沒有主動發送 LINE／Discord、操作 production DB、讀取 Secret value 或修改 IAM／Scheduler。
- 沒有 rollback；previous revision `00029-vmc` 保留。
- 平台 health 通過，但線上通知業務流程依授權未做人工 smoke test；下一次既有 Scheduler 將自然使用新 revision。

## 結論

部署與安全驗證成功，沒有觸發 rollback 條件。TASK-008 可結案。
