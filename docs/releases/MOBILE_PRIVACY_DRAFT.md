# Mobile privacy and support draft — NOT PUBLISHED

盤點日期：2026-09-16；TASK-199；source baseline：`d83bd4b1e64bad119f780344fbde6d57c378f308`。
狀態：供 Owner／獨立 reviewer 決策的內部草稿，尚未核准、生效或作為正式隱私政策發布。
Repository 公開此文件也不代表政策發布；不得直接貼成 App Privacy／Data Safety 已完成答案。
本文件不凍結 UI 或首版範圍，不改既有 [release gates](MOBILE_RELEASE_MATRIX.md)。

## 1. 證據範圍與讀法

- `SOURCE`：由上述 baseline 的程式／lockfile 可證明的能力；不等於某個 runtime 已啟用。
- `VENDOR`：官方文件描述的 SDK／平台行為；仍須核對實際解析版本、設定及候選 artifact。
- `UNKNOWN`：缺少外部證據或 Owner 決策；不是「否」、不收集、無限期保存或已通過。
- 檢查僅讀 source、套件版本與公開官方文件；未讀 private config、runtime assets、環境檔、token 或使用者資料。
- TASK-198 已有本人 TestFlight／Google 與核心操作證據；本輪未重新檢查 IPA、archive、裝置或雲端設定。
  那些既有結果不證明隱私 manifest、所有 provider 或所有保存／刪除路徑均已驗證。

## 2. SDK 與平台盤點

版本依 [pubspec.yaml](../../clients/flutter_app/pubspec.yaml) 與 [pubspec.lock](../../clients/flutter_app/pubspec.lock)。
本機 generated registrants 是可再生且 gitignored 的中間產物，只作比對線索，不能取代 exact binary 清單。

| 元件／版本 | SOURCE 使用方式 | 尚需證據 |
| --- | --- | --- |
| Flutter runner | README 記錄 Flutter 3.47.0；實際 candidate engine 版本須由建置紀錄綁定 | exact archive 的 Flutter framework、manifest 與 required-reason API |
| `flutter_line_sdk` 3.0.0，Git `c48b87b430f2d0c7b50926d04cc4de8050ad413a` | Android／iOS 登入；`NativeLineLogin` 只要求 `openid`，讀 nonce-bound ID token | 原生 LINE SDK 解析版本、其 manifest／傳輸／保存行為；不能把「未要求 profile」等同 SDK 不處理其他資料 |
| `google_sign_in` 7.2.0；Android 7.2.16／iOS 6.3.0 adapter | `authenticate()` 後只取 ID token 交 Mobile API；未另請求業務 API scopes | 原生 GoogleSignIn 與所有轉遞依賴的解析版本、設定、manifest；plugin 版本不是原生 SDK 版本 |
| `flutter_secure_storage` 10.3.1；Darwin 0.3.2 | App session、安裝識別、快取與偏好儲存；iOS `first_unlock_this_device`；Android 隔離 namespace 且不作 backup migration | 裝置 Keychain／儲存生命週期與第三方實作；不可承諾解除安裝即清除全部資料 |
| `http` 1.6.0 | App 到 Mobile API 的 HTTPS transport；請求包含登入憑證或 App bearer 與功能資料 | runtime／代理層日誌及保留設定；使用 HTTPS 不表示端到端加密或伺服器無法讀取 |
| 原生 Apple bridge | `AuthenticationServices`／`CryptoKit`，沒有另加 Apple Flutter 登入套件；requested scopes 為空 | provider/runtime 是否啟用、真機登入與撤銷流程；不是已完成 Apple lifecycle |
| 轉遞套件 | lockfile 另含 `jni` 1.0.3、`jni_flutter` 1.0.2、`path_provider` 2.1.6／foundation 2.6.0 等 | local Android registrant 含 JNI；local iOS registrant 列 LINE／secure storage／Google。套件存在不能推定所有平台均打包或傳送資料 |

登入 source：[integration.dart](../../clients/flutter_app/lib/integration.dart) 的 `NativeLineLogin`／`NativeGoogleLogin`／
`NativeAppleLogin`、[AppleAuthorizationBridge.swift](../../clients/flutter_app/ios/Runner/AppleAuthorizationBridge.swift)。
[LINE 官方 Flutter 說明](https://developers.line.biz/en/docs/line-login-sdks/flutter-sdk/)確認 plugin 包裝兩個原生 SDK；
[scope 對照](https://developers.line.biz/en/docs/line-login/integrate-line-login/#scopes)將 `openid` 與 profile／email 分開。
[Google iOS disclosure](https://developers.google.com/identity/sign-in/ios/app-privacy)明列 SDK 可能收集使用者識別，
以及供防詐／推估概略位置的 IP。這是 VENDOR 待納入評估的資料，不能由本 App 只讀 ID token 而排除。

### Manifest 與權限

`git ls-files -- '*PrivacyInfo.xcprivacy' '*Podfile.lock' '*Package.resolved' '*gradle.lockfile'` 在 baseline 無結果。
這只證明 repository 未追蹤這些檔案；**已簽署 archive 的 manifest 是否存在、內容與聚合結果均為 UNKNOWN**。
[Apple SDK 要求](https://developer.apple.com/support/third-party-SDK-requirements/)列有 Flutter、GoogleSignIn 等元件；
[privacy manifest 說明](https://developer.apple.com/documentation/bundleresources/privacy-manifest-files)要求將適用宣告打包。
後續 candidate 應保存去識別化的 resolved native dependencies、bundle manifest 清單、required-reason API 檢查與
Xcode privacy report 結果，綁定同一 artifact；本輪未產生／重建／簽署候選。

TASK-200 補上 [unsigned CI inventory](../../clients/flutter_app/ios/README.md#unsigned-ci-privacy-inventory-task-200)：
在既有 fictional archive 建好後，唯讀掃描 packaged `.xcprivacy` 與兩個 SPM lock 位置，不再建置或碰已簽署 IPA。
報告區分未宣告／空陣列／false／型態異常；原生版本保留 missing、unknown 與 conflict，不拿 Dart plugin 版本代替。
工具與 CI integration 的實際證據見 [TASK-200 report](../coordination/reports/TASK-200.md)。它只檢查已知欄位型態，
不驗證 Apple enum／API reason 正確性；alias 不是 SDK provenance，resolved 不是 linked，宣告也不是 runtime 行為。
`inspected_evidence_sha256` 只綁定盤點摘要，不是整份 archive digest；CI 成品不是本人手機的 build2。
因此即使 scan complete，上述已簽署 candidate、Xcode privacy report、全 SDK coverage 與商店答案仍保持 UNKNOWN。

2026-09-17 實際 unsigned CI run35126415121/job104896495291 完成盤點：13份manifest（12bundle／1framework），
已知欄位型態均可解析，但App根目錄manifest缺席、7份元件alias未知。兩個SPM lock相同、各有2個未對照identity；
已對照原生版本為GoogleSignIn9.2.0、LINE5.17.0、AppAuth2.1.0、GTMAppAuth5.0.0、GTMSessionFetcher3.5.0、
GoogleUtilities8.1.3、Promises2.4.1，非Dart plugin版本。GoogleSignIn宣告有8筆collected-data entry，
不代表App runtime必然收集8類，也不能由plugin自身空宣告推論SDK不收集。精確source／digest／表格見TASK200 report。
結果為 `INVENTORY_COMPLETE_WITH_FINDINGS`，不是合規PASS；不由未知alias推論某SDK沒有manifest。
合併後main/run35127733708/job104900884114的盤點摘要相同，綁定974ff5ad195057e49c3facd776948990a9c391c2；
沒有檢查或更新已安裝的signed build2。此unsigned證據不可改填前述candidate UNKNOWN。

### TASK-201：公開來源對照，不是成品來源認證

2026-09-17以TASK200同一公開fictional CI log核對到`app-check`及
`interop-ios-for-google-sdks`的fetch來源；它們是Google登入相依圖的一部分，不等於App啟用
Firebase、reCAPTCHA或所有App Check功能。新增兩個exact identity alias；實際resolved版本
仍以後續同一job的lock盤點為準，不把上游最低版本或本次查閱tag冒充成品版本。

| 公開來源（固定版本） | 可支持的命名對照／限制 |
| --- | --- |
| [GoogleSignIn 9.2.0](https://github.com/google/GoogleSignIn-iOS/blob/9.2.0/Package.swift) | production target引用AppCheckCore；`app-check` → `app_check`，不是新增App功能 |
| [AppCheck 11.3.2](https://github.com/google/app-check/blob/11.3.2/Package.swift)／[Interop 101.0.0](https://github.com/google/interop-ios-for-google-sdks/blob/101.0.0/Package.swift) | `interop-ios-for-google-sdks` → `google_interop`；此處tag用來查來源，不宣稱是CI解析版本 |
| [AppAuth 2.1.0](https://github.com/openid/AppAuth-iOS/blob/2.1.0/Package.swift) | AppAuth package的AppAuthCore target含manifest，新增`AppAuth_AppAuthCore.bundle` |
| [GTMSessionFetcher 3.5.0](https://github.com/google/gtm-session-fetcher/blob/v3.5.0/Package.swift) | Core target含manifest，新增`GTMSessionFetcher_GTMSessionFetcherCore.bundle` |
| [GoogleUtilities 8.1.3](https://github.com/google/GoogleUtilities/blob/8.1.3/Package.swift) | Environment／Logger／UserDefaults resources，新增`GoogleUtilities_GoogleUtilities-Environment.bundle`、`GoogleUtilities_GoogleUtilities-Logger.bundle`、`GoogleUtilities_GoogleUtilities-UserDefaults.bundle` |
| [Promises 2.4.1](https://github.com/google/promises/blob/2.4.1/Package.swift) | FBLPromises target含manifest，新增`Promises_FBLPromises.bundle` |

六個bundle名稱是由package／resource target推導的exact-name hints，並非本輪已重建觀察；
未經下一次CI盤點不可宣稱未知數已減少。不得靠prefix、substring、大小寫修正或未知內層bundle的
已知外層名稱認領元件；同名也不保證來源。未知component新增固定finding，避免root存在／lock完整時
被總結成沒有finding的`INVENTORY_COMPLETE`。其他private名稱、位置、URL與revision持續不回顯。

[LINE 5.17.0 manifest](https://github.com/line/line-sdk-ios-swift/blob/5.17.0/LineSDK/LineSDK/Resource.bundle/PrivacyInfo.xcprivacy)
為982bytes，LF摘要`bb1ec69d3627a15a47714e3310aef25af11a27dcf1af4b1b58916823a0e02637`，
恰與TASK200 unsigned inventory ordinal10相同。這是**內容對應**，不是SDK provenance；通用
`Resource.bundle`不能全域貼成LINE，工具不做hash-driven attribution，也不改寫TASK200歷史unknown結果。
上游該檔宣告linked UserID供App functionality、UserDefaults reason `CA92.1`；僅為vendor宣告，
不可直接複製成第一方app manifest，亦不是runtime驗證。

[Android main manifest](../../clients/flutter_app/android/app/src/main/AndroidManifest.xml)宣告 INTERNET 並關閉 backup；
[iOS Info.plist](../../clients/flutter_app/ios/Runner/Info.plist)含 LINE／Google callback scheme。
這兩個 source 檔未宣告相機、麥克風、通訊錄或定位讀取權限；此觀察不涵蓋 merged manifest、SDK 網路 IP 或 OS 行為。

## 3. 第一方資料流盤點

下表描述 SOURCE，不直接等同商店問卷分類。相同帳號的 hash／opaque ID 可被系統關聯，不能稱匿名。

| 資料／用途 | 來源與去向 | 保存／限制與 source |
| --- | --- | --- |
| 登入識別、身份綁定與狀態 | provider ID token 交 Mobile API 驗證；穩定 subject 連結 Person | `AuthIdentityRecord` 保存 provider／subject／Person／狀態與時間；不以 email／name 自動合併；S1／S2 |
| token 內其他 claims | App 傳送完整 ID token，驗證器只產生身份所需的 `VerifiedAssertion` | 「不取 email／name 作業務欄位」不表示 token 不含它們，也不證明所有傳輸／日誌沒有它們；S1 |
| App 工作階段與防重 | 安裝隨機 ID、platform、attempt／idempotency ID、App access／refresh | access 留記憶體；refresh／待處理狀態存 SecureStore；伺服器有 installation hash、session、refresh hash／加密重播及期限；期限不是資料刪除承諾；S2／S3 |
| 姓名與隊務資格 | Person 顯示名稱、權限／狀態與隊務資料；本人可更新顯示名稱 | 資料庫另有 formal name、管理備註與 legacy Member 欄位；Basic `/me` 投影不等於取得全部欄位，也不等於這些既有資料已刪除；S2／S3 |
| 賽事／活動與出席 | App 查詢活動並提交本人回覆；後端保存關聯與時間 | 依權限提供本人、成員清單／出席統計或幹部視圖；Basic 功能不等於資料僅本人可見；S2／S3 |
| 身份審核與通知 | pending review 可提交文字；通知中心取得授權通知並記錄讀取狀態 | 審核訊息／管理操作稽核／通知受眾與讀取紀錄有持久欄位；須另定內容保存與可見角色；S2／S3 |
| 離線資料與偏好 | Person、賽程、通知快取依 installation／Person 分區；外觀、onboarding、診斷選擇在裝置端 | 離線唯讀；帳號快取清除與 installation 偏好不是同一範圍；不能聲稱登出清除所有 Keychain／SDK／後端資料；S3／S4 |
| Apple credential foundation | 若 runtime 啟用並成功交換，後端保留獨立加密 provider refresh credential 與 hash；接收簽署事件 | 僅 repository 能力；revoked 狀態或通知 receipt 不等於刪除資料／主動向 Apple 撤銷 token；S1／S2 |
| 匿名當機 foundation | 使用者 opt-in 後在裝置端保存固定類別、UTC 日、flavor、platform、第一方 frame 指紋 | 預設關閉、最多 8 筆／8 KiB；讀寫時依 7 日規則剔除過期資料，非背景定時刪除保證；opt-out purge；無 network sink；S4 |

- S1：[provider_verifiers.py](../../shared_lib/shared_module/provider_verifiers.py)、[mobile_api.py](../../shared_lib/shared_module/mobile_api.py)。
- S2：[models.py](../../shared_lib/shared_module/portal_data/models.py)、[mobile_repository.py](../../shared_lib/shared_module/portal_data/mobile_repository.py)。
- S3：[API routes](../../apps/mobile_api/app.py)、[integration.dart](../../clients/flutter_app/lib/integration.dart)、[basic_app.dart](../../clients/flutter_app/lib/basic_app.dart)。
- S4：[anonymous_crash.dart](../../clients/flutter_app/lib/anonymous_crash.dart)、[main.dart](../../clients/flutter_app/lib/main.dart)、[local_preferences.dart](../../clients/flutter_app/lib/local_preferences.dart)。

目前 real client 未接 APNs／FCM 真實推播或 crash upload provider；後端 fake device-registration foundation 不等於
candidate 收集真實推播 token。未發現第一方廣告／資料出售程式路徑，不據此保證所有 SDK、營運契約或 tracking 均為否。
雲端 request logs、IP／User-Agent、資料庫備份、存取人員、region／跨境處理與處理者契約仍為 UNKNOWN；未查正式資料。

### 第一方 manifest 決策紀錄（TASK-201，尚不打包）

Source baseline：`974ff5ad195057e49c3facd776948990a9c391c2`；本task不改App或SDK行為。
以下是供下一次candidate核對的候選分類，**不是核准問卷或可直接產生plist的規格**。
分類依[Apple data types](https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacycollecteddatatypes/nsprivacycollecteddatatype)
及[第一方／SDK資料宣告界線](https://developer.apple.com/documentation/bundleresources/describing-data-use-in-privacy-manifests)
於2026-09-17查閱；下列Apple enum省略共同前綴`NSPrivacyCollectedDataType`。

| Source事實／精確入口 | 候選分類與linked線索 | 尚缺的宣告依據 |
| --- | --- | --- |
| S1登入exchange → S2 `AuthIdentityRecord.provider_subject`／Person；S3 `Native*Login`傳ID token | UserID；持久關聯帳號，不能寫unlinked／匿名 | exact candidate provider／token額外claims的保留與營運用途；不能宣稱只傳ID |
| S1 `update_profile` → S2 `PersonRecord.display_name` | Name或UserID，取決於使用者實際填姓名或暱稱；與Person關聯 | 公開版欄位語意、既有資料來源；不能由允許自由文字斷言只收姓名 |
| S3 login/refresh的installation ID → S2 `MobileSessionRecord.installation_id_hash`與Person | DeviceID候選（安裝識別不是硬體ID）；hash可關聯，不是匿名化 | Apple裝置層分類與安裝生命週期、實際保留/用途核對 |
| S1出席／Event回覆與identity review `append` → S2持久紀錄 | OtherUserContent候選；review訊息另需評估CustomerSupport，均可關聯Person／identity | 依公開版功能區分隊務內容與客服內容；不能把所有文字當Email或訊息服務 |
| S1 notification read／操作稽核 | ProductInteraction或OtherUsageData候選，來源linked | 逐端點用途與保留；業務操作不自動等於分析追蹤 |
| S4 anonymous crash queue與S3 SecureStore偏好 | 本機診斷／偏好，第一方source無上傳sink | 不因此豁免SDK、OS或雲端另有的收集；新增上傳時重開分類 |

Required-reason API檢查：Runner內`AppDelegate`／`SceneDelegate`／`AppleAuthorizationBridge`
未找到第一方直接呼叫UserDefaults、file timestamp、disk capacity、system uptime或active keyboard
API；Dart的`DateTime.now()`不是看到「時間」就能填入SystemBootTime reason的依據。
`SecureStore`經Darwin plugin呼叫Keychain，不等同第一方直接UserDefaults。
此為**有限source檢查**，不是對Dart VM、編譯結果、所有轉遞SDK或runtime call graph的證明。
Flutter及SDK自己的reasons須各自保留，不能把vendor-only理由照抄到App以消除root缺席。
依[Apple required-reason規則](https://developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api)，
真正新增第一方相關API時必須把exact API、用途、有效reason與打包證據一起review。

結論：root manifest缺席是未收斂事項，不是自動拒審證明，也不是「不用manifest」的結論。
暫不加入空白或`tracking=false`／no-collection占位plist。下一步由Owner確認第6節的責任主體、
實際用途／無廣告追蹤承諾、公開版功能與資料處理政策；工程端再核對runtime／第三方／雲端事實，
獨立review後才新增App宣告與Xcode resource membership測試。未知資訊不能靠Owner一個「同意」變成技術證據。

## 4. 不可直接套用的商店答案

[Apple App Privacy](https://developer.apple.com/app-store/app-privacy-details/)將 collection 與離機後保留時間相關聯，
也涵蓋第三方伙伴；純裝置處理與暫時驗證資料須分開判斷，不能忽略後端實際持久資料。
[Play Data Safety](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en)涵蓋離機傳輸與 SDK，
暫時處理亦須依表單規則回答；closed testing 不是只限 internal testing 的豁免。
User ID、Name、Device ID、User Content／Product Interaction 等僅為待逐項映射候選，不是核准答案。
SDK IP 的用途、linked／tracking、sharing／service-provider 例外及選填揭露條件均須以確切證據判斷。

[Apple 刪除指引](https://developer.apple.com/support/offering-account-deletion-in-your-app/)允許人工處理所需時間，
但要求可在 App 啟動、說明處理時間並確認完成；一般 App 不能以強制聯絡客服替代，停用也不是刪除。
Sign in with Apple 的 token 撤銷是另項履行要求。
[Play 刪除指引](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en)要求適用 App 的內部入口與
外部 web 申請資源。TASK-199 的請求／查詢 foundation 不是完成刪除、可公開使用入口或政策合規證據。

## 5. 可供核准的使用者文字草稿（尚未生效）

下列文字連同 `UNKNOWN` 欄位須由 Owner 核准及核對實際 candidate，才可移到正式頁面；禁止原樣發布占位內容。

> NTUBTOB 隱私與資料使用說明｜政策版本／生效日：UNKNOWN。
> 服務提供者／資料責任主體：UNKNOWN。隱私與支援聯絡方式：UNKNOWN。
>
> App 使用登入服務提供的帳號識別、隊務帳號資料、賽程與出席回覆，提供登入、身份核對與隊務功能。
> 若您使用身份審核訊息或通知功能，系統也會處理您提交的內容、相關狀態與必要操作紀錄。
> 資料會依授權角色供隊務作業使用；確切可見對象與管理者範圍：UNKNOWN，須核對公開版功能。
>
> 登入由所選的 LINE、Google 或 Apple 服務完成，App 將登入證明交後端驗證，不要求您把 provider 密碼交給隊務管理員。
> 登入供應商可能依其服務處理相關識別或網路資料；正式供應商清單、政策連結與其他處理者：UNKNOWN。
> 第一方資料不作廣告或出售的正式承諾須由責任主體核准，目前尚未形成生效政策。
>
> 裝置會保存維持登入、離線唯讀及偏好所需資料。目前 source 版本未提供裝置推播或當機報告上傳。
> 當機診斷預設關閉；同意後僅在此裝置保留受限的去識別化診斷，關閉此選項會清除其佇列。
> 帳號、出席、審核、稽核、登入紀錄、備份與支援資料的保存期限、刪除例外及依據：UNKNOWN。
>
> 登出、停用帳號與提出刪除申請並不等於資料已刪除。正式申請入口、身份核對、處理範圍、期限與完成通知：UNKNOWN。
> 更正、查閱或其他資料權利的可用管道與處理方法：UNKNOWN。請勿在支援回報傳送密碼、權杖或完整個人資料。
> 政策變更通知方式與適用地區／年齡：UNKNOWN。

支援頁文案草稿：

> 遇到問題時，請提供 App 版本／Build、問題發生的大致時間與不含個資的操作步驟。
> 請勿附上密碼、登入權杖、帳號識別或未遮蔽的個人資料；一般錯誤回報不能作為刪除申請人身份證明。
> 正式支援聯絡方式、公開支援／隱私頁與刪除申請網址尚待確認。本文件本身不能收件，也不表示申請已受理。

## 6. Owner 決策與後續可驗證工作

| 未定事項 | 需要的決策／證據；未完成前維持 UNKNOWN |
| --- | --- |
| 主體與管道 | 法律／營運主體、可公開名稱、有效支援與隱私聯絡方式、公開 policy／support／deletion URL、無登入可達證據；不由校名或 App 名推定法律主體 |
| 資料生命週期 | 每類帳號／identity／出席／通知／審核／稽核／備份資料的期限、刪除方式與例外依據；不能用 token TTL 當保存期限 |
| 刪除履行 | 成員歷史關聯、重新註冊、provider 撤銷、pending／restricted 帳號的可用管道、時限、通知與稽核；本 task 禁止真實刪除 |
| 第三方與雲端 | exact native dependency／manifest 報告、Google IP 等 SDK 事實、雲端日誌／備份／region／存取角色與處理者契約；不讀 secret 或真實資料 |
| 發行政策 | 首版能力、適用地區／年齡、資料權利與依據、廣告／出售承諾、政策版本及變更通知；均不由這份技術盤點定案 |
| 驗收與發布 | Main／獨立 review、exact candidate questionnaire 對照與正式頁可達性；本草稿不授權 store 填寫或網站發布 |

TASK-199原始官方連結查閱日期為2026-09-16；TASK-201新增來源為2026-09-17，詳見各段。
平台規則提交前仍須重新核對；本輪只交source facts與未發布草稿。
