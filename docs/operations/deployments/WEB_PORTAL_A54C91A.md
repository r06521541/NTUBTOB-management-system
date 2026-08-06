# Web Portal production deployment — a54c91a

- 日期：2026-08-06（Asia/Taipei）
- 結果：成功；未需要rollback
- PR：[ #50 ](https://github.com/r06521541/NTUBTOB-management-system/pull/50)
- Exact merge commit：`a54c91aa9eb788a47bd9448445abdd1f88658174`
- GitHub Actions run：`31078936423`（Python 3.10，成功）
- Cloud Build：`8351e941-aee6-42ce-ab86-5f40a4d42cba`
- Previous／rollback revision：`web-portal-00037-lhx`
- New revision：`web-portal-00038-cv8`
- Image digest：`sha256:20a3fd3057d060e12ae0f8d0836735d904dc936bde88b8d6a79587f5680e97cc`

## 驗證

- `web-portal-00038-cv8`為Ready／Active／ContainerHealthy並承接100% traffic。
- 單次不跟隨redirect且不讀body的checks：`GET /`為200，`GET /demo/`為404。
- Runtime identity與既有Secret references通過wrapper contract；未讀取Secret value。
- 未人工invoke LINE callback、未讀取production callback logs、未連production DB或修改IAM／Secret／Scheduler／schema／data。

## 待Owner重現

Owner需在LINE App內從`/attendance`重新登入一次，回報大約操作時間及最後落點。之後Work只查詢固定`line_login_callback destination=<category>`診斷，不讀取request URL、query、code、state、cookie或身分資料。

