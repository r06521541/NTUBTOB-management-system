# Mobile release readiness matrix

狀態日期：2026-08-31
範圍：去識別化 repository contract；不包含 store、provider、signing、cloud、production 或真實裝置操作。

## 使用方式與證據語意

本矩陣區分四個 release channel，避免把 Android Closed Testing 的較小產品範圍推論成公開版 readiness，或把
repository 靜態檢查推論成 iOS archive／TestFlight／App Review 證據。

- `repo gate`：可由 source、tests、artifact inspection 或文件 review 驗證；仍須綁定 exact commit／artifact。
- `external gate`：必須由未來 Owner 核准的 store console、provider、macOS/Xcode、真機或 production 工作包取得。
- `blocked`：目前已有明確缺口；不得以人工宣告、空值、debug 設定或其他 channel 的證據替代。
- Store 表單規則可能改變；提交當下須由 Owner 在 console 重新核對實際問題，不以本文件當成平台規則快照。

所有實際 URL、bundle/package identity、帳號、聯絡資料、client/provider ID、certificate、profile、team ID、Secret、
device identifier 與 backend endpoint 都不得填入本矩陣。

TASK-170 的永久 Android package identity 已由 Owner 明定；其 exact candidate record 不填在本矩陣，而依
[`ANDROID_CLOSED_TESTING_CHECKLIST.md`](ANDROID_CLOSED_TESTING_CHECKLIST.md) 以 package/version/artifact SHA 綁定。
該 checklist／validator 只接受外部提供的去識別化 evidence，不查詢或操作 Play Console、signing、runtime 或裝置。

## Channel baseline

| Channel | 近期產品範圍 | Repository candidate gate | 尚需外部證據／目前結論 |
| --- | --- | --- | --- |
| Android Closed Testing | Basic-only；Officer／Admin、push、deep-link delivery、匿名 crash reporting可延至公開版 gate | API 36、release flavor/package/version、HTTPS real-client config、external signing injection與AAB inspection須由同一 TASK 的 Android lane及Main驗證 | Play Console track、tester access、Data Safety問卷與實機安裝仍是Owner-gated；repository通過不等於已上傳或可公開 |
| Android public | Basic + 經產品核准的公開版能力 | Closed Testing gate全部重跑於exact public artifact；Officer／Admin若納入，須有server authorization與UI evidence | `blocked`：push、deep link、匿名 crash、production backend、公開metadata/privacy/deletion與公開實機matrix尚未完成 |
| iOS TestFlight | staging／real client；只作隔離測試，不宣稱production | `staging:real + Release + testflight`、explicit version/build、非debug bundle identity、外部signing metadata及既有auth validator；repository已有Apple code exchange／加密credential／notification revocation foundation | macOS/Xcode archive、codesign/profile、App Store Connect、TestFlight install與真機auth/session仍未驗證；provider capability、runtime binding及smoke仍為external gate，不可推論公開版或App Review readiness |
| iOS public | production／real client；公開版必須提供Sign in with Apple | `production:real + Release + app-store`，且Apple runtime、entitlement、provider readiness與完整public gates全部通過 | `blocked/fail-closed`：repository marker仍為`not_implemented`；repository lifecycle foundation不等於provider、signing、deployment或App Review evidence，不得以review例外、private override或TestFlight結果繞過 |

## Compliance 與 release evidence matrix

| Gate | Android Closed Testing | Android public | iOS TestFlight | iOS public | 可接受的去識別化 evidence |
| --- | --- | --- | --- | --- | --- |
| Privacy policy／資料使用 | 送出前須確認測試者可取得且內容符合candidate實際行為 | required | 測試說明與收集行為必須與staging candidate一致 | required | exact policy revision/hash、review date、redacted route availability；不複製使用者資料 |
| Play Data Safety | 提交該track前依console當下要求完成，答案須與exact AAB一致 | required並以public artifact重核 | N/A | N/A | redacted questionnaire version、reviewer、artifact SHA；不得記console帳號或Secret |
| Apple App Privacy | N/A | N/A | 上傳／測試前依App Store Connect當下問題核對staging行為 | required並以public artifact重核 | redacted answers/version與artifact SHA；不得記account/team/provider material |
| 帳號刪除申請 | App內已有申請說明，但仍須確認store要求的可達路徑／URL與處理流程 | required；`blocked`直到申請入口、identity verification、scope、retention與完成回覆可review | 同Android；TestFlight tester必須能找到申請方式 | required；`blocked`直到App Review可啟動申請且metadata一致 | 畫面測試、去識別化request lifecycle、公開URL availability與policy revision；不得放真實申請人 |
| Store metadata | listing草稿須明確標示Basic-only closed test與已知限制 | 名稱、描述、分類、support/privacy/deletion URLs、screenshots、content rating及review notes完整 | beta description、test notes、support/privacy資訊、登入前置條件與限制完整 | 公開metadata、screenshots、privacy/deletion及Apple登入描述與artifact一致 | redacted field checklist、locale list、screenshot manifest/hash；不保存console session |
| Version／identity／signing | repo與AAB inspection須fail closed；簽章材料repository外部注入 | exact public package/version/signature allowlist | repo validator要求Release、version/build、bundle identity與外部signing metadata | 同TestFlight，另須Apple entitlement/provider gate | exact artifact hash、version/build、deidentified signer fingerprint comparison result；不記private key/password/profile payload |
| Real-device core flow | 至少一部支援裝置驗證install/upgrade/cold start、LINE/Google login、refresh/logout、schedule/attendance/offline | 支援OS／device matrix與accessibility/performance擴充 | 支援iPhone／iOS真機驗證install、cold start、login/link/recovery、refresh/logout、Keychain與offline | 同TestFlight，加Apple login及公開production流程 | 去識別化device class/OS、scenario、result、artifact hash；不記裝置識別碼、個資或provider token |
| Push permission／delivery | 不阻塞首個Closed Testing candidate，但UI不得假稱已送達 | required：opt-in/deny/settings、token lifecycle、notification centre、foreground/background delivery | 若candidate未提供push，metadata/test notes須明示；不得宣稱完成 | required | fictional payload tests + future redacted provider/real-device delivery evidence；不記token或通知內容 |
| Deep link | 不阻塞首個Closed Testing candidate；不得宣稱notification destination已驗證 | required：cold/warm/unauthenticated/unauthorized/unknown target fail closed | 若未啟用，beta notes明示且不得以UI route test代替OS delivery | required | allowlisted route tests與去識別化OS delivery matrix；不得記auth state/token |
| Anonymous crash reporting | 不阻塞首個Closed Testing candidate；不得宣稱已收集 | required：opt-in/notice與redaction驗證，禁止token、姓名、通知內容、payload | 若未啟用，beta notes明示 | required | synthetic crash receipt與redaction assertion；不保存原始敏感event/body |
| Production backend／auth | 不得使用production；closed candidate只能指向Owner核准的隔離環境 | required：exact HTTPS endpoint、mobile auth/session/capability、rollback與post-check | 不得使用production；只允許隔離staging | required：Apple token verification、identity linking/recovery、session、capability、rate/error boundaries與rollback | redacted configuration classification、contract tests、exact deployment/artifact refs；不記endpoint、Secret或production rows於本矩陣 |
| Review／rollback | Main整合review、hosted CI與exact AAB inspection | 獨立Release/Security review、public hosted gates與rollback plan | Main + Release/Security review；macOS/Xcode/TestFlight evidence另附 | 完整public review、App Review response plan與rollback/disable path | immutable commit/artifact SHA、named gate結果與bounded rollback reference |

## 帳號刪除 contract

App 的支援頁目前提供「帳號刪除申請」說明，要求使用既有球隊聯絡管道、先驗證申請人與範圍、不要傳送密碼或
權杖，並明示登出不等於刪除。這是必要 UX，但不是完整 store compliance 證據，也不表示後端資料已刪除。

公開 release 前必須由獨立工作包確認：

1. 使用者與 reviewer 不需取得管理權限即可找到並啟動申請；若平台要求公開 URL，metadata 與 App 內路徑一致。
2. 驗證身分不要求密碼、provider token或過量個資；request ID與狀態回覆可稽核但不揭露資料內容。
3. 明列 account、登入identity、球隊歷史／法定或安全保留資料的處理範圍、期限與例外；不得把「停用」誤稱為「刪除」。
4. 完成／拒絕／需補件皆有安全回覆；重試不建立重複副作用。真實資料mutation仍需獨立Owner gate與post-check。

## Evidence record template

每個實際 channel candidate 應另產生受控、去識別化 evidence，至少包含：

```text
channel: <android-closed|android-public|ios-testflight|ios-public>
commit_sha: <40-char reviewed SHA>
artifact_sha256: <exact artifact hash>
version_build: <public version + monotonic build>
repository_gates: <exact commands/results>
external_gates: <named evidence refs or BLOCKED>
privacy_form_revision: <redacted revision/ref>
real_device_matrix: <deidentified scenario result ref>
production_authorization: <not_applicable|exact future Owner approval ref>
remaining_blockers: <explicit list>
```

不得填 `PASS` 來代表未執行的外部 gate；未知、未授權或無證據一律記為 `BLOCKED`。
