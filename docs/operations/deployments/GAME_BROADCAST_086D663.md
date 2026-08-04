# Game Broadcast Production Deployment Package

Status：`deployed`
Task：`TASK-008`
Environment：production
Target：`game-broadcast-service`
Git commit：`086d663831cf49ddaa5f8413edd8508d1f6bf596`
Project／region：`ntubtob-schedule-405614`／`asia-east1`

## Expected change

Invitation and cancellation requests calculate one fresh Asia/Taipei time snapshot per request instead of reusing container import time. The existing `today_begin + 11 days` query limit remains unchanged.

## Impact declaration

- Database/schema impact：none。
- Secret/env contract：unchanged from current P0 production contract。
- Authentication boundary：private，must remain unchanged。
- Deployment mutation：one Cloud Build, image push, Cloud Run revision and traffic update。
- Artificial notification/data invocation：none。
- Scheduled side effect：existing Scheduler remains enabled and may naturally invoke the new revision after deployment。

## Pre-deploy baseline

- Previous revision：`game-broadcast-service-00029-vmc`。
- Previous digest：`sha256:02de096bf0b42cb34c659a2580856eda7c2171be74e08aab8d4d71e8351eb8df`。
- Traffic：100% to previous revision。
- Scheduler jobs：reminder 09:30 daily；cancellation 16:30 and invitation 17:30 on configured weekdays／Sunday, Asia/Taipei。

## Execution checklist

- [x] Owner deployment approval recorded。
- [x] Exact commit and clean deployment scope verified。
- [x] 24 game broadcast tests pass。
- [x] CI success reconfirmed。
- [x] Account/project/region and current revision reconfirmed read-only。
- [x] Secret version state and private IAM reconfirmed without values。
- [x] At least 30 minutes before next Scheduler invocation。
- [x] Shared library artifact freshly built and identified by hash。
- [x] Deployment command executed from controlled source tree。
- [x] Build ID, new digest and revision captured。
- [x] Private boundary, runtime identity and Secret references verified。
- [x] Temporary environment file removed without displaying content。

## Stop／rollback

Do not call notification endpoints. On a defined failure, route 100% traffic back to `game-broadcast-service-00029-vmc`; verify recovery and retain the failed revision for investigation.

## Result

Result：`success`

- Window：2026-08-04 23:48–23:52 Asia/Taipei。
- Approved source tree：commit `086d663831cf49ddaa5f8413edd8508d1f6bf596`; verified tree hash `63736bc4fb5aef2a53437ab52a114bcee102b2d6`。
- Python 3.10 tests：24/24 `OK`。
- GitHub Actions：run `30922220358`, `success`。
- Shared artifact SHA-256：`95E00F6CE83B6F08DDBCB1CBFFFFE23107DF53B9FC7D5B7E542A0328D72CBCF9`。
- Cloud Build：`80b086fc-f0c1-4f6b-a4e6-3acb456a1d6b`, `SUCCESS`。
- New revision：`game-broadcast-service-00030-pgg`, ready／healthy, 100% traffic。
- New image digest：`sha256:7301a529d18506f5f46832090421924cd7c40e2726233d0062fbc2ea1a4c8698`。
- Runtime identity：unchanged。
- Secret references：database password latest、Weather API key 2、LINE access token 1。
- Authentication：private；no `allUsers` invoker binding。
- Scheduler：unchanged and enabled。
- Artificial endpoint invocation：none。
- External notification／production data write observed by this deployment procedure：none。
- Rollback：not performed；previous revision `game-broadcast-service-00029-vmc` retained。
- Temporary environment file：removed。
- Remaining limitation：online notification behavior was intentionally not smoke-tested。
