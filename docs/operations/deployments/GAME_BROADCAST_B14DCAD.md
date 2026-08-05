# Game Broadcast Startup Safety Production Deployment

Status：`deployed`
Task：`TASK-018`
Target：production `game-broadcast-service`
Commit：`b14dcad3d1261772c8dc00898ba1caca114ce941`
Rollback baseline：`game-broadcast-service-00030-pgg`

## Result

- Window：2026-08-05 13:16–13:22 Asia/Taipei。
- Bundled Python：game broadcast 27/27 tests通過；compile與`git diff --check`通過。
- Python 3.10 CI：run `30975939328`、job `92209817045`成功。
- Shared artifact SHA-256：`90121D13B504EEDEAC8BB78DBDAF365D312E17591F3B150275C1670FC246F362`。
- Cloud Build：`b4081955-261f-4e41-a160-c31376e3b1ff`，`SUCCESS`。
- Built digest：`sha256:091a429733593c91aaba877a9224abca7951116ada9b42671131e462174d7799`。
- New revision：`game-broadcast-service-00033-mdp`，Ready／Active／ContainerHealthy／ContainerReady均為True，承接100% traffic。
- Authentication：service維持private；runtime identity未變。
- Secret references：database password `latest`、weather API key version `2`、LINE access token version `1`；未讀取Secret value。
- Scheduler三個jobs的state、schedule、method與target未漂移。
- Temporary filtered env與deployment worktree中的env source copy均已清理，內容未顯示。
- Rollback：未觸發；`00030-pgg`保留。

## Fixed tag deployment finding

Cloud Build原始deploy step使用固定image字串`:tag1`。雖然新digest已push，Cloud Run template字串沒有改變，因此未建立新revision，且先前rollback後traffic明確pin在`00030-pgg`；step回報舊`00031-s65`仍為0% traffic。

Work確認新tag digest後，依核准的deployment範圍改以精確digest更新service，建立`00033-mdp`；先驗證image、identity與Secret references，再將100% traffic顯式切至`00033-mdp`。此流程沒有擴張至其他服務或設定。

固定tag會造成部署no-op與追溯困難，應另立repository任務改為immutable tag／digest並提供跨平台preflight wrapper。

## Side effects and limits

- 未人工invoke任何health或business endpoint。
- 未人工發送LINE／Discord通知、未人工讀寫production DB。
- 未修改Secret、IAM、Scheduler、credential或其他服務。
- Owner已接受既有Scheduler自然呼叫新revision及既有通知／DB副作用；本次未等待下一次自然排程，因此線上業務整合尚未由實際排程證明。
