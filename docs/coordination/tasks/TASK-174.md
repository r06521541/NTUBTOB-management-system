# TASK-174：Sign in with Apple Provider Lifecycle Foundation

## Task metadata

- type: `delivery`
- delivery_group: `task-174-apple-provider-lifecycle`
- acceptance_level: `L3`（auth／provider protocol／schema；repository-only）
- base: `dc18f264929057eb9c23e3efd0f9d2e5dbe79ae9`
- branch: `codex/task-174-apple-provider-lifecycle`
- report_to: `main-work`
- owner_approved: 2026-08-31
- future_apple_enrollment_subject: `individual`（只記分類；不授權enrollment／付款）

## Product outcome

在不設定 Apple Developer provider、不注入真實 Secret、不部署及不連 production 的前提下，補齊 iOS native Apple
authorization code、後端 token exchange、durable encrypted provider credential 與 server notification revocation 的
repository foundation。現有 nonce-bound ID token 與 stable `sub` 仍是登入身份 assertion；email、name、relay email、
native user identifier及 profile hint 不得用於自動合併帳號。

## Writer claim

- actor_id: `/root/task174_apple_lifecycle_writer`
- role: `codex-writer`
- claim_id: `task-174-apple-lifecycle-writer-20260831`
- lease_version: 6
- scope: Apple native credential envelope、Mobile API/provider lifecycle、durable schema、offline tests及release evidence
- owned_paths:
  - `clients/flutter_app/ios/Runner/AppleAuthorizationBridge.swift`
  - `clients/flutter_app/lib/integration.dart`
  - `clients/flutter_app/test/apple_auth_test.dart`
  - `shared_lib/shared_module/provider_verifiers.py`
  - `shared_lib/shared_module/mobile_api.py`
  - `shared_lib/shared_module/portal_data/models.py`
  - `shared_lib/shared_module/portal_data/mobile_repository.py`
  - `shared_lib/tests/test_mobile_api_service.py`
  - `migrations/versions/0010_apple_provider_lifecycle.py`
  - `tests/portal_data/**`
  - `apps/mobile_api/app.py`
  - `apps/mobile_api/bootstrap.py`
  - `apps/mobile_api/revision_readiness.py`
  - `apps/mobile_api/.env_example.yaml`
  - `apps/mobile_api/openapi.json`
  - `apps/mobile_api/README.md`
  - `apps/mobile_api/tests/**`
  - `tools/portal_data_migration_readiness.py`
  - `tools/portal_data_phase_c_migration.py`
  - `clients/flutter_app/README.md`
  - `clients/flutter_app/ios/README.md`
  - `docs/releases/MOBILE_RELEASE_MATRIX.md`
  - `docs/coordination/reports/TASK-174.md`

Writer 只能修改 owned paths，須 self-review／self-test，完成後主動送 Main immutable SHA、dirty paths、tests、findings、
remaining limits 與 external mutations。Main 是正式 acceptor；writer 不得自行建立 PR、合併、部署或開始下一 task。

Lease 2只補入`0010`不可分割的runtime revision readiness、canonical migration verifier及non-secret env key-name example。
既有TASK-157 staging operator／launcher與TASK-164 production event rollout artifact仍固定各自已部署revision，不在本task修改；
repository head變更不代表任何環境已升級。

Lease 3只修正Main依Apple官方wire範例發現的server-notification contract：Sign in with Apple notification外層claims
不要求`exp`，`event_time`是Unix秒而非毫秒；須新增無`exp`成功、秒級時間、錯誤毫秒／額外claim fail-closed regression。

Lease 4另修正Main發現的encryption key separation：既有`MOBILE_REFRESH_REPLAY_KEY` cipher只負責app session refresh
successor，獨立`MOBILE_API_APPLE_PROVIDER_CREDENTIAL_KEY` cipher只負責Apple provider refresh credential；constructor、bootstrap
與focused regression須證明兩者不混用。

Lease 5修正independent reviewer的P1 rollout finding：新runtime的core readiness只接受既有additive安全集合
`0008_mobile_notification_delivery`、`0009_event_management_writes`與`0010_apple_provider_lifecycle`，讓目前0008／0009環境可先部署
相容runtime再migration；Apple exchange／notification仍以獨立exact-0010 gate關閉。未知／future revision繼續fail closed，且須有
pre-0010時LINE／Google可用、Apple不可用的route regression。既有已部署舊runtime不宣稱可在migration-first順序持續服務。

Lease 6補入reviewer P2：除了不同env名稱，bootstrap必須在不記錄key material的前提下拒絕
`MOBILE_REFRESH_REPLAY_KEY == MOBILE_API_APPLE_PROVIDER_CREDENTIAL_KEY`，使session與provider cipher的用途隔離成為可執行
invariant，並加入bootstrap focused regression；不允許以相同Fernet key啟用Apple。

## Independent reviewer claim

- actor_id: `/root/task170_release_security_review`
- role: `advisor/reviewer`
- claim_id: `task-174-apple-auth-security-reviewer-20260831`
- lease_version: 1
- write: `read-only`
- report_to: `/root`
- scope: immutable pushed TASK-174 SHA的Apple wire、one-shot exchange、cipher／token no-disclosure、notification replay／revocation、migration compatibility與LINE／Google isolation

Reviewer不得修改working tree、commit、push、PR或外部狀態；收到Main提供的immutable SHA後，以Git blobs驗收並主動送回
ACK、heartbeat（若超過10分鐘）與completion verdict／tests／findings／limits／external mutations。

## Required behavior

1. Native iOS bridge只回傳bounded `identity_token`與single-use `authorization_code`；Flutter只把兩者連同既有raw nonce、
   attempt、installation與platform送到Apple exchange。不得傳送或保存email、name、relay email或native user identifier。
2. Server先本機驗證ID token signature／issuer／audience／expiry／nonce，再以exact client與runtime-injected client secret將
   authorization code交換一次。HTTPS、content type、timeout、bounded response、safe error與returned ID-token subject
   correlation全部fail closed；code、token、client secret及provider body不得進log／exception／audit。
3. 成功交換所得refresh token只以獨立runtime encryption key加密後持久化；repository不得保存plaintext、client secret或
   signing key。登入idempotency與code replay必須拒絕重複provider mutation；unknown／timeout不得自動重送code exchange。
4. 新migration需讓舊runtime安全共存，加入bounded Apple provider credential及notification idempotency state。不得修改
   既有identity唯一鍵；stable verified `sub`仍是唯一provider subject。
5. 新public notification endpoint在任何mutation前驗證Apple signed JWS與exact audience；只接受已知event type及bounded
   time/idempotency claims。`consent-revoked`／`account-deleted`須原子停用Apple identity、撤銷其mobile sessions與provider
   credential；email forwarding事件因本系統不保存provider email，只做去識別化idempotent receipt。未知、ambiguous或
   malformed事件fail closed且不得洩漏payload。
6. Apple lifecycle runtime預設disabled。缺client、client-secret、encryption key、notification audience或schema readiness時，
   只停用Apple能力，不降低LINE／Google安全，也不得讓App Store release marker變成ready。
7. 帳號刪除／主動token revocation、Apple credential-state真機檢查、provider capability、notification URL、signing與
   TestFlight仍是後續Owner gate；本task不得假稱已完成。

## Verification budget

- Test-first focused Apple verifier／exchange／notification／repository／OpenAPI／Flutter tests。
- migration upgrade from `0009_event_management_writes`，以及 PostgreSQL 15／16 hosted matrix。
- affected Mobile API、portal-data、Flutter Apple、iOS shell contract與quality checks。
- 一位獨立 Auth/Security reviewer驗收immutable SHA。
- 一個ready PR；required hosted CI全綠且無conflict才依standing authorization squash merge。

## Stop conditions

- 需要真實Apple帳號、App ID、Team/provider/client識別值、private key、client secret、certificate/profile、Secret payload、
  App Store Connect、付費、cloud/runtime/deployment、production DB/data或真機個資。
- 無法在不保存plaintext provider token的情況下完成durable contract；server notification schema無法由官方規格與測試
  明確限定；需要改變Person合併規則或跨provider identity ownership。
- dirty paths超出本task與Main coordination files，或base／branch／claim不一致。

## External evidence boundary

實機advisor只回報`iphone_available`、`ios_supported`與Developer Program狀態分類；它不構成provider、signing、archive、
TestFlight或真實Apple登入證據。Apple官方文件只用於外部wire contract，repository tests必須完全fictional、offline。
Owner已選擇未來Apple發布主體分類為`individual`；真正enrollment前仍須由Owner確認Apple當下顯示的費用、公開seller
資訊與條款。本決定不包含帳號、法律姓名、付款資料或任何外部mutation。

## Communication drill gate

Owner要求TASK-174驗收前先證明跨agent／sibling task主動回報。`main-notify-20260831-a`的4個live agents均依序送達
ACK／heartbeat／completion；`sibling-notify-20260831-a`中iPhone guide因未回exact thread id首次失敗，Main改為在packet
直接提供canonical id後，以`sibling-notify-20260831-b`重演通過。近期同repository sibling tasks最終2/2通過；演練全程
read-only、external mutations為0。後續Main依`COLLABORATION.md`保持active bounded wait，不在delegation執行中先結束turn。
