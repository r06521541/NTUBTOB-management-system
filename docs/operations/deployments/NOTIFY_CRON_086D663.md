# Notify Cron Production Deployment Package

Status：`deployed`
Task：`TASK-009`
Target：production `notify-cronjob-service`
Commit：`086d663831cf49ddaa5f8413edd8508d1f6bf596`
Rollback：`notify-cronjob-service-00009-k8z=100`

Expected outcome：LINE credentials are excluded from build/runtime plain env input; LINE access token is bound from Secret Manager version 1; service remains private. No schema or migration change.

Rollback is operationally available but security-degraded because the previous revision predates TASK-003. No endpoint smoke test was authorized or performed.

## Result

- Result：`success`。
- Window：2026-08-05 00:16–00:19 Asia/Taipei。
- Approved source tree：commit `086d663831cf49ddaa5f8413edd8508d1f6bf596`; tree `63736bc4fb5aef2a53437ab52a114bcee102b2d6`。
- Python 3.10 tests：4/4 `OK`；GitHub Actions run `30922220358` success。
- Shared artifact SHA-256：`CB15BE4142A771021555969EC3863B1AAD157087F726B171E3DD9BA1217EB04D`。
- Cloud Build：`20152b06-02be-44d0-b50c-b92fc95877e7`, `SUCCESS`。
- New revision：`notify-cronjob-service-00010-z2x`, ready／healthy, 100% traffic。
- New digest：`sha256:94751e129fe7d1d88304ebad716326f15023858252c6e28816b41d5220173fb5`。
- Secret references：database password latest、LINE access token 1；plain `CHANNEL_SECRET` 不再存在於 runtime env names。
- Authentication：private；runtime identity unchanged；Scheduler unchanged。
- Artificial invocation／observed deployment notification／production data write：none。
- Rollback：not performed；`00009-k8z` retained。
- Temporary env：pre-existing residual removed before build and generated file removed after deployment。
- Limitation：online notification behavior intentionally not smoke-tested；existing Scheduler will naturally use the new revision。
