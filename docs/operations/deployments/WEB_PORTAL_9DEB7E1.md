# Web Portal production deployment — 9deb7e1

- 日期：2026-08-06（Asia/Taipei）
- 結果：成功；未需要rollback
- PR：[ #49 ](https://github.com/r06521541/NTUBTOB-management-system/pull/49)
- Exact merge commit：`9deb7e11311d5ccdb4131cb3b13a318a6bceca60`
- GitHub Actions run：`31076620682`（Python 3.10，成功）
- Cloud Build：`a1902e48-ed13-480d-9097-e1b180fbc4c5`
- Service：`web-portal`
- Region：`asia-east1`
- Previous／rollback revision：`web-portal-00036-2p2`
- New revision：`web-portal-00037-lhx`
- Image digest：`sha256:ed0ecb1dfcc5c9b012826f5ab4d37b3c130a727e0bdb8a3997fd420e9a85664d`

## Preflight

- Active account為Owner既有部署帳號；project精確為`ntubtob-schedule-405614`。
- `web-portal-00036-2p2`在部署前Ready且承接100% traffic。
- LINE Login與session Secret version `1`均為Enabled；未讀取Secret value。
- Wrapper dry-run與26項Web Portal deployment wrapper tests通過。
- Exact commit已merge至`origin/main`，deployment branch工作樹乾淨。

## Deployment與驗證

- Wrapper確認immutable image tag與digest、新revision Ready、runtime identity、既有Secret references、public boundary及production demo gate。
- `web-portal-00037-lhx`為Ready／Active／ContainerHealthy，承接100% traffic。
- 單次不跟隨redirect且不讀body的HTTP checks：`GET /`為200；`GET /demo/`為404。
- Rollback未觸發；若未來確認回歸，任何traffic變更仍需新的明確授權，不得把本次rollback核准視為持續授權。

## 未執行

- 未人工執行LINE Login callback、LINE通知、production DB query/write或管理操作。
- 未修改Secret、IAM、Scheduler、schema、data或其他服務。
- Owner仍應以實際瀏覽器人工確認新版視覺、帳號頁、首頁導覽與登出體驗。

