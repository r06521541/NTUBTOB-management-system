# TASK-110 Codex implementation report

## Execution checkpoint and scope

- Goal: Basic-only native LINE authentication and canonical mobile API integration while preserving the TASK-105 fake foundation.
- Core files: Flutter composition/models/ports/session/cache, Android/iOS runner configuration, tests, and this report only.
- Invariants: OpenAPI is canonical; no invented wire fields; access token memory-only; refresh/session state installation-isolated; offline is read-only; Officer/Admin and real push remain fake/deferred.
- Minimum evidence: exact dependency resolution, formatter/analyze/full tests, explicit fake debug APK, merged manifest/signing/artifact and secret/endpoint review.
- Deferred: real LINE/API calls, staging/production values, iOS runtime/signing, release signing/deployment, Officer/Admin real APIs, push/deep links.

Repository writes stayed within `clients/flutter_app/**` and this report. Branch started clean at `1ddc7f1e42020c19f4c66a9cfe480c3ab121d5f8` on `codex/task-110-flutter-basic-api`.

## Delivered

- Exact dependencies: `flutter_line_sdk 2.7.2`, `flutter_secure_storage 10.3.1`, and `http 1.6.0`. Versions and SDK constraints were checked against their official publisher/pub.dev package metadata and downloaded package source; the lockfile pins all transitives.
- Compile-time composition fails closed. Development requires explicit `APP_FLAVOR=development` plus `CLIENT_MODE=fake` and rejects service values. Staging/production require `CLIENT_MODE=real`, a strict HTTPS URL without userinfo/query/fragment, and a numeric LINE channel ID. No value is committed.
- Native LINE adapter requests only `openid`, injects a CSPRNG nonce, requires matching returned nonce and raw ID token, and exchanges the exact OpenAPI flat body with a CSPRNG attempt ID. Coordinator models pending/cancel/error/unavailable/stale/duplicate outcomes; tests never call LINE.
- Typed, fail-closed models cover session, Basic person/capabilities, games, own/replied-team attendance, both qualifications, all five attendance values, mutation result and notification outcome. Unknown response fields are tolerated; missing required/nullable-required fields, unknown enum values, non-UTC wire timestamps, and non-Basic accounts fail typed parsing.
- HTTP transport uses the configured HTTPS base, JSON, explicit 15-second timeout, and redacted contract errors. Access tokens stay in memory. Refresh token, refresh attempt, installation ID, mutation intent, cache index/data, and `logout_pending` use platform secure storage with Android namespace/no backup migration and iOS this-device-only Keychain accessibility.
- Session refresh is single-flight, preserves an attempt ID across uncertain/lost responses, rotates durable refresh before accepting access, retries one request once after 401, does not refresh on other statuses, clears terminal sessions, and blocks while logout is uncertain.
- Basic integration implements `/me`, game list/detail, attendance, and attendance mutation with durable idempotency key. Offline mutation makes zero transport calls. A 5xx uncertain mutation GET-reconciles and accepts success only when own reply matches; otherwise the same key remains durable for retry.
- Versioned cache is partitioned by installation and person, displays fixed persisted last-sync time, and provides offline read-only Basic data. Logout clears its partition.
- Real composition performs installation bootstrap, cold-start refresh, login/logout, Basic me/games load, and offline-cache fallback. Development still uses the unchanged TASK-105 deterministic fake UI/repositories; no UI duplication was introduced for flavor selection.
- Android: minSdk 24, main INTERNET permission, backups disabled, no release signing block. Exact LINE 2.7.2 requires AGP 9 Built-in Kotlin and an after-evaluation library compileSdk 35 override because its own script pins 33 while resolved AndroidX metadata requires 34+. App identifier remains reviewed fictional `com.example.ntubtob_fictional_client` pending a separate production decision.
- iOS: target remains 15; LINE callback scheme uses `line3rdp.$(PRODUCT_BUNDLE_IDENTIFIER)` and `lineauth2` query scheme. No channel value, team, profile, or signing material is present.

## Domain review correction

- Basic real UI now navigates from the games list to a concrete game-detail/attendance page, reads canonical game and attendance resources, displays only replied team/guest players, exposes all five attendance controls, and renders distinct mutation pending, error, and uncertain/reconcile states. Offline cached lists disable navigation and reply controls.
- Auth UI now distinguishes booting, logged out, provider active, exchanging, identity pending, account unavailable, session expired, cancelled, unavailable, recoverable network, malformed contract, logout pending, offline, and authenticated states. The canonical Error envelope/code enum is typed; bodies and tokens are never included in displayed/logged errors.
- Failure classification is fail closed: only a recoverable transport failure with an existing cache enters offline mode. Contract parsing failures and terminal auth failures retain distinct states even when cache exists.
- Authorized request concurrency compares the failed access token with the current generation. Ten simultaneous old-token 401 responses share one refresh, then each original request is replayed at most once.
- Secure refresh persistence is transactional from the client's perspective: a secure-store write/delete failure clears memory access and rolls back durable refresh state. Restarted `logout_pending` is retried and cleared only after an idempotent terminal outcome.
- Durable mutation intent parses its stored logical reply. The same reply reuses the same idempotency key; a different reply first reconciles the old reply, then either blocks without PUT or starts a new key only after the old result is confirmed.
- `GamePage` types both required `items` and nullable `next_cursor`; Basic loading follows canonical cursors until null and rejects a repeated cursor. No pagination field was invented.
- Native auth tests cover cancel, stale completion, duplicate completion, provider/exchange states, and canonical `identity_pending`/`account_unavailable` classification. Fake versus real composition and Basic-only navigation are explicitly tested.

### Second review correction

- A replayed request returning a second 401 now clears both memory access and durable refresh/attempt state before throwing typed `SessionExpiredException` (or a non-session canonical `ApiError`). It never issues a third request.
- Native login has an injectable, production-default 35-second timeout around the entire provider operation, including platform setup/login. Timeout maps to recoverable auth UI, performs no exchange, and never exposes nonce/token data.
- Native login accepts only canonical `android` or `ios` platform values in both UI mapping and coordinator. Windows/web/desktop/unknown targets fail unavailable before LINE or API calls.
- An empty canonical games result renders a dedicated icon/message and `目前沒有可顯示的賽事` semantics rather than a blank person-only list.
- HTTP response stream consumption is covered by the same timeout and maps stream socket/timeout failures to `NetworkException`, preserving consistent offline classification.

### Main Work transport-ambiguity correction

- A `NetworkException` thrown only after the attendance PUT begins is treated as an uncertain mutation outcome. The client preserves the already-durable logical reply/key and immediately performs the canonical attendance GET.
- If GET proves `own_reply == desired`, the intent is cleared and the existing unknown-outcome success is returned. A mismatching reply, GET network/timeout failure, auth failure, malformed response, or any other result that cannot prove the desired reply retains the same intent/key and throws `MutationUncertainException`.
- Explicit PUT HTTP outcomes remain outside this ambiguity path: canonical 403/409/422/auth/contract errors are parsed and surfaced directly without attendance reconciliation. Existing 5xx reconciliation is unchanged and shares the same proof helper.
- Tests assert `PUT -> GET` ordering and key clear/retention for Network+match, Network+mismatch, and Network+reconcile-Network; a 409 test proves no GET. Widget evidence confirms transport ambiguity renders uncertain UX rather than mutation error.

### Authorized-request source correction

- `SessionController` now converts a `NetworkException` to the dedicated `AuthorizedRequestNetworkException` only around the target authorized `api.send(method, path)` call. Pre-request refresh and refresh after an explicit 401 retain their ordinary recoverable `NetworkException` classification.
- `BasicApi.reply()` reconciles only the dedicated target-request exception, so it cannot infer that a PUT was attempted when token acquisition failed. No exception-message matching is used.
- Tests prove that a cold request whose refresh fails makes zero PUT and zero attendance-reconcile calls, and that an explicit PUT 401 followed by refresh-network failure makes no attendance-reconcile call. Both preserve the durable mutation intent without reporting `MutationUncertainException`; all prior post-PUT ambiguity and explicit 4xx coverage remains.

## Verification

- `flutter pub get`: passed; exact direct versions resolved.
- `dart format --output=none --set-exit-if-changed .`: passed on clean source tree, `7 files (0 changed)`. An earlier invocation after build encountered a generated Gradle dex path disappearing during directory traversal; build output was removed and the exact gate then passed.
- `flutter analyze`: passed, no issues.
- `flutter test`: passed, 71 tests. Correction coverage explicitly includes 10 concurrent 401s/one refresh/one replay each, terminal second-401 session clearing/no third request, secure-store failure rollback, logout-pending restart, native timeout/unsupported-platform zero-call gates, cancel/stale/duplicate, response-stream network classification, every auth-state semantic, explicit empty games semantics, Basic-only/fake-real composition, offline reply disablement, paged games, game detail/own and replied-team attendance, all five controls, mutation pending/error/uncertain UX, same-key retry, different-reply block, 5xx reconciliation, PUT-Network match/mismatch/reconcile-failure paths, pre-PUT and post-401 refresh-network source isolation, and explicit-error no-reconcile behavior, plus all retained TASK-105 tests.
- `flutter build apk --debug --dart-define=APP_FLAVOR=development --dart-define=CLIENT_MODE=fake`: passed. Final source-correction APK `build/app/outputs/flutter-apk/app-debug.apk`, 185,453,774 bytes, SHA-256 `DAB31F19EE69268E84A764EB7C98E13D9EB9DC7BCF7CD361D756F2B220F8A332`.
- Merged manifest: INTERNET present; `allowBackup=false`; `fullBackupContent=false`; debug build marked debuggable; no cleartext override. `apksigner verify --print-certs` passed and identified only `CN=Android Debug`. Source/repository review found no release `signingConfig`, keystore, alias, or store file.
- Secret scan (`api key`, client secret, private key, password, bearer patterns) found only the obvious unit-test string `Bearer new`; no credential value. Runtime URL scan found only XML namespaces/schema documentation. Config scan found names only (`API_BASE_URL`, `LINE_CHANNEL_ID`), no base URL/channel value.
- `git diff --check`: passed. Cumulative writer-scope/status review performed before staging and commit.

Toolchain: Flutter 3.47.0 stable / Dart 3.13.0, Microsoft OpenJDK 17.0.20+8, TASK-107 Android SDK. Build automatically installed official Android platforms 33 and 35 plus CMake 3.22.1 into `C:\Users\USER\.codex\toolchains\task-107\android-sdk`; existing platform 36 remained. Gradle caches are under `C:\Users\USER\.codex\toolchains\task-107\gradle-home`. Cleanup: remove those specific SDK package directories with `sdkmanager --uninstall` where supported, and stop Gradle then remove the task-107 Gradle cache. A disk-full failure initially corrupted the reproducible Gradle transforms cache; after Owner freed space, that exact cache was stopped/removed and rebuilt successfully.

## Limitations and side effects

- No real LINE/API request, external message, push, database operation, deployment, upload, PR, merge, release signing, or production state change occurred.
- Android native smoke was a successful fake debug build only; no emulator/hardware was available for interactive login. iOS runtime/build/signing remains gated on macOS/Xcode.
- Flutter emits a forward-looking warning that `flutter_line_sdk 2.7.2` still uses legacy Kotlin plugin detection. The task requires exact 2.7.2 and the current build passes; a future dependency task should reassess when an approved newer official release exists.
- The APK/build directory is ignored and is not committed. Official SDK packages and caches listed above are the only external writes.
