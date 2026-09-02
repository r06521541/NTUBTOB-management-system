# iOS TestFlight candidate checklist

這份清單把「repository可先完成」與「Apple enrollment／macOS／App Store Connect才可完成」分開。它不是Apple平台規則
的永久快照；每次實際提交仍須由Owner核對當下Console問題。不得在文件、聊天、log或evidence中保存Apple account、
Team ID、App ID、certificate/profile識別值、private key、provider值、裝置識別碼或token。

## 目前結論

- iOS staging／real Release source已由hosted macOS/Xcode以`--no-codesign`編譯；這只證明source可編譯。
- `APPLE_SIGN_IN_REPOSITORY_STATUS`仍為`not_implemented`，所以actual signed candidate inspector必須回BLOCKED。
- Apple Developer enrollment、App ID/capability、distribution certificate/profile、App Store Connect app、signed IPA、
  TestFlight upload/install及真機登入仍是外部gate。
- 本清單與inspector不會建立、修改或上傳任何Apple資源。

## A. Enrollment等待期間可完成

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
  --artifact <private-path-to-signed.ipa> \
  --expected-version <public-semver> \
  --expected-build <public-positive-integer> \
  --previous-build <public-nonnegative-integer>
```

工具先建立bounded snapshot，拒絕unsafe archive，再以macOS固定`codesign`／`security cms`唯讀檢查。成功輸出只包含：

- exact artifact SHA-256／size及public version/build；
- bundle/minimum-iOS/signature/distribution-profile/Apple-entitlement match分類；
- 明確的`provider_runtime_verified=false`、`testflight_upload_verified=false`及`real_device_verified=false`。

不得把`CONTRACT_TEST`當candidate evidence。actual mode在repository marker未ready時必須先停止，且不得為了讓工具PASS而
手動改marker或跳過codesign/profile/entitlement檢查。

## D. Upload前仍需的外部gate

1. Exact App ID已啟用Sign in with Apple，reviewed entitlement已綁定target；App與profile的embedded entitlement一致。
2. Staging provider/client與server authorization-code lifecycle、credential state及revocation evidence已由獨立review接受。
3. App Privacy、beta notes、support/privacy/deletion入口與exact candidate行為一致；未完成push、deep link或crash upload須明示。
4. Candidate只連隔離staging runtime/data；Secret/runtime ownership另有deidentified evidence，不能由IPA inspection推論。
5. Main接受immutable commit與IPA evidence後，Owner才在App Store Connect執行一次upload／tester release gate。

## E. TestFlight後的最小真機matrix

- install、cold start、upgrade與reinstall分類；
- LINE／Google login、session refresh/logout及identity conflict/recovery；
- Apple login在支援裝置上的allow/cancel/error/retry、link/re-auth/logout；
- schedule、Game／Event attendance、offline read與online mutation fail-closed；
- Keychain/session在restart後的預期狀態；
- support/privacy/deletion入口可達。

Evidence只記device class、iOS major/minor、scenario/result、commit與IPA SHA；不記UDID、Apple/LINE/Google帳號、subject、
token、個資、screen raw dump或provider response。
