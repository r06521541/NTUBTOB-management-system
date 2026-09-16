# iOS TestFlight candidate checklist

這份清單把「repository可先完成」與「Apple enrollment／macOS／App Store Connect才可完成」分開。它不是Apple平台規則
的永久快照；每次實際提交仍須由Owner核對當下Console問題。不得在文件、聊天、log或evidence中保存Apple account、
Team ID、App ID、certificate/profile識別值、private key、provider值、裝置識別碼或token。

## 目前結論

- 截至2026-09-16，隔離staging／real／Basic候選已完成真實簽署、Apple接收及僅Owner內測分發；
  Owner確認`1.0.0 (1)`安裝與六項核心smoke、`1.0.0 (2)`更新後進首頁。逐build證據與限制見
  [`TASK-198 report`](../coordination/reports/TASK-198.md)，不以本清單取代exact artifact／run evidence。
- `APPLE_SIGN_IN_REPOSITORY_STATUS`仍為`not_implemented`，default TestFlight inspection仍BLOCKED；明確
  `--artifact-only`只檢查既存IPA完整性，不授權upload／release，見`IOS_CLOUD_BUILD_RUNBOOK.md`。
- 既有Apple資源與已保存的簽署／上傳Secrets不重建、不要求重填。Apple登入後端仍未備妥；LINE／Apple真機登入、
  logout及更廣裝置情境仍未驗證。Google成功不替代其他provider證據。已上傳候選的sidefile audit仍失敗且內容未知；
  Owner只接受各該run的本人內測剩餘風險，不代表完整清理PASS或未來錯誤豁免。
- TestFlight文案與App Privacy repository事實已整理於
  [`IOS_APP_STORE_CONNECT_ANSWERS.md`](IOS_APP_STORE_CONNECT_ANSWERS.md)；公開privacy/support URL、App內完整帳號刪除、
  第三方SDK privacy、出口合規與年齡分級仍不可填PASS。
- TASK-198／IOS-TF-01已授權Main在reviewed工具、隔離staging、既有資產、成本與custody邊界內推進exact candidate及
  Owner-only internal TestFlight，不需逐SHA再要求Owner phrase；遇task明列stop仍停止。本清單與inspector本身不執行upload。
- fictional selection diagnostic成功不再被workflow刻意改成失敗；其真正nonzero仍失敗，且不證明real signing或public readiness。
  本次邊界調整沒有新增live signing/upload controller。
- Repository支援入口已接到歡迎頁與登入前畫面，原有首頁入口仍支援離線；這是source/widget evidence，尚未進入已安裝的
  build2。靜態資料使用與聯絡申請說明不是公開privacy policy、可執行帳號刪除或store compliance PASS。

## A. Mac／Xcode與Apple資源建立前可完成

1. 保持bundle identity、iOS 15 minimum、staging／real／Release／testflight組合及version/build contract不漂移。
2. 確認beta scope只使用隔離staging backend；不得填production endpoint或把TestFlight成功推論為production ready。
3. 準備不含帳號資料的beta description、test notes、support/privacy/deletion入口與known limitations。
4. 保留Sign in with Apple repository marker為blocked，直到provider capability、entitlement、server lifecycle與真機證據由
   獨立Release／Security review接受。
5. 對每個candidate預留去識別化record：commit SHA、IPA SHA-256、version/build、inspector結果、外部gate狀態及limits。

## B. Enrollment完成後的Owner-visible分類

由Apple事項兄弟task帶Owner操作並只回分類，不回原始值：

| 項目 | 可回報分類 |
| --- | --- |
| Membership | `active_personal`／`active_organization`／`pending`／`blocked` |
| App identifier | `exact_available`／`absent`／`ambiguous` |
| Sign in with Apple capability | `enabled_exact`／`absent`／`ambiguous` |
| Distribution certificate | `available_valid`／`absent`／`ambiguous` |
| App Store profile | `exact_valid`／`absent`／`ambiguous` |
| App Store Connect app | `exact_available`／`absent`／`ambiguous` |

`ambiguous`、mixed identity、unexpected existing resource或任何需要顯示／保存private material的情況立即停止，由Main另立
bounded decision。Owner不得把private key、profile payload、account/email或原始identifier貼入聊天。

## C. Signed IPA產生後的離線gate

只在Owner核准的macOS builder，對已存在且不再修改的IPA執行：

```sh
python3 -m tools.ios_candidate_inspector inspect \
  --artifact-only \
  --artifact <private-path-to-signed.ipa> \
  --expected-version <public-semver> \
  --expected-build <public-positive-integer> \
  --previous-build <public-nonnegative-integer>
```

工具先建立bounded snapshot，拒絕unsafe archive，再以macOS固定`codesign`／`security cms`唯讀檢查。成功輸出只包含：

- exact artifact SHA-256／size及public version/build；
- bundle/minimum-iOS/signature/distribution-profile/Apple-entitlement match分類；
- 明確的`provider_runtime_verified=false`、`testflight_upload_verified=false`及`real_device_verified=false`。

不得把`CONTRACT_TEST`當candidate evidence。default mode在repository marker未ready時必須先停止，且不得為了讓工具PASS而
手動改marker或跳過codesign/profile/entitlement檢查。
IOS-TF-01的internal candidate使用明確artifact-only結果搭配下節scope/runtime/custody gate；不是default/public-ready PASS。

## D. Upload前仍需的外部gate

1. Exact App ID已啟用Sign in with Apple，reviewed entitlement已綁定target；App與profile的embedded entitlement一致。
2. Staging provider/client與server authorization-code lifecycle設定、schema及部署契約已由獨立review接受；未驗證的device、
   credential-state／revocation情境明列限制，不把需先安裝候選的證據倒置為首次internal upload前提。
3. App Privacy、beta notes、support/privacy/deletion入口與exact candidate行為一致；未完成push、deep link或crash upload須明示。
4. Candidate只連隔離staging runtime/data；Secret/runtime ownership另有deidentified evidence，不能由IPA inspection推論。
5. Main依IOS-TF-01接受immutable commit、exact App/version/build/IPA evidence及獨立signing/upload custody後，由reviewed工具
   執行單次upload、processing reconciliation及僅Owner的dedicated internal group分發；沒有reviewed live controller時不得執行。
   不確定結果唯讀核對，不盲目重傳；私密artifact不能用預設公開CI artifact保存，cleanup不明即停止。
6. 裝機後完成下節核心驗收。Public-ready marker、public release、其他tester分發及production均不是internal upload成功的推論；
   未完成privacy／deletion或provider情境不得改填PASS，仍依task禁止真實資料刪除等邊界。

## E. TestFlight後的最小真機matrix

下列是完整matrix，不是要求每輪全部重做。TASK-198已接受的Google登入、連網重開、離線標示、恢復連線後重開、
賽事詳情與限定虛構出席修改／還原不重複；build2另有更新進首頁確認。只補未驗證或被新diff影響的slice。

- install、cold start、upgrade與reinstall分類；
- LINE／Google login、session refresh/logout及identity conflict/recovery；
- Apple login在支援裝置上的allow/cancel/error/retry、link/re-auth/logout；
- schedule、Game／Event attendance、offline read與online mutation fail-closed；
- Keychain/session在restart後的預期狀態；
- support/privacy/deletion入口可達。

Evidence只記device class、iOS major/minor、scenario/result、commit與IPA SHA；不記UDID、Apple/LINE/Google帳號、subject、
token、個資、screen raw dump或provider response。
