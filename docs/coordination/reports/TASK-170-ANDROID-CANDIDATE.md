# TASK-170 Android candidate contract writer report

## 2026-09-02 secure operator correction

- Real runtime/provider values and signing path/alias/passwords are no longer Dart defines or environment variables. They enter the
  repository operator through hidden input and reach Gradle through one nonce-authenticated loopback connection held only in memory.
- Gradle emits the four runtime values only into the exact Android runtime asset required by the app. The public release-contract asset
  retains digests only. Strict AAB inspection now reads the actual runtime asset and recomputes both digests, preventing contract/payload drift.
- Flutter startup loads the Android Closed runtime asset inside the same guarded zone as binding initialization. Development fake mode
  and non-Android-Closed composition retain their existing behavior.
- `tools.android_candidate_operator` requires clean exact `main == origin/main`, monotonic version history and one typed approval; it
  suppresses child output, constructs a minimal environment, builds and strictly inspects one AAB, then reports sanitized metadata.
  It cannot create/rotate a key, upload, open Console, deploy or operate a device.
- A local signed fictional release build completed through the new memory channel. The channel uses a fixed LF nonce challenge from
  Gradle to the already-listening repository operator, followed by exactly eight length-framed UTF-8 values; malformed peers receive no
  private input. The temporary fictional key and repository build directory were deleted; real
  configuration/signing/provider/account/device/store/cloud/production state was not accessed.

## Delivered

- Android `release` is now an explicit `android-closed` channel. It accepts
  only package `tw.org.ntubtob.portal`, API 36, `staging:real`, and Basic scope;
  production, development, fake, Officer/Admin, missing, duplicate, extra, or
  mixed release defines fail before compilation.
- The release requires an externally approved lowercase SHA-256 for both the
  exact staging API origin and the ordered LINE/Android Google/Web Google
  provider tuple. The generated schema-2 contract contains only the digests,
  never the endpoint or provider IDs.
- The pubspec version (`0.1.0+1`) remains the source of truth. Both external
  version fields must match it, and the candidate code must be greater than a
  canonical non-negative previous package version code. `0` is valid only
  after external evidence establishes that the package has no earlier version.
- Existing signing boundaries remain fail closed: an external JKS/keystore,
  alias, privately supplied passwords, and exact post-build signer fingerprint
  are mandatory; repository-resident/debug/contract-shaped candidate signing
  identities are rejected.
- The AAB inspector now accepts `android-closed` rather than generic candidate
  mode and binds byte hash/size, package, version transition, API 36,
  staging/real/Basic channel, the two approved configuration digests, archive
  integrity, and strict signer verification in one sanitized JSON result.
- Reviewer correction: the inspector snapshots the caller artifact once and
  then uses only that immutable copy for bundle metadata, archive validation,
  hashing, and all signer reads. A pinned bundletool 1.18.3 runtime, resolved
  through the fixed Gradle wrapper in offline mode, validates the complete AAB
  and parses the protobuf manifest for actual package, version name/code, and
  min/target/compile SDK. Signature-shaped ZIP placeholders no longer qualify.
- Contract parsing and Gradle URI/base64 failures now emit fixed categorical
  errors without caller-controlled keys/values or chained parser causes.
- P1/P2 correction: all four standard Gradle wrapper components are versioned
  and bound to canonical SHA-256 values. The inspector reads and verifies them
  once, launches only a private snapshot, and supplies a constructed minimal
  child environment. Signing/provider/private variables and Java/Gradle option
  injection are not forwarded. Missing, linked, or changed wrapper components
  fail before execution. Duplicate Dart-define failures are categorical and no
  longer echo the decoded key.

## Regression and verification

- Current continuation verification: the combined operator/release/evidence suite passed 50/50; CI workflow contracts passed 12/12;
  full Flutter analyze reported no issues and full Flutter tests passed 316/316. Per-file Black checks passed for all four changed Python
  files, Dart format changed zero files, and `git diff --check` passed with line-ending conversion warnings only.
- The final current-tree fictional build passed through the nonce-authenticated, length-framed channel and produced a 52.6 MB AAB.
  Strict inspection of that same AAB passed with 655 entries, package `tw.org.ntubtob.portal.contracttest`, version `0.1.0 (1)`,
  min SDK 24, target/compile SDK 36, `android-closed`, Basic scope, exact runtime/contract digest agreement, archive integrity and exact
  fictional signer agreement. The AAB, build directory and two-day fictional keystore were removed immediately afterward.
- Independent review of the first immutable continuation commit requested two P1 corrections. The operator now binds the commit returned
  by preflight and rechecks exact clean `main == origin/main == reviewed commit` immediately before Gradle, after build and again after
  retaining the candidate. Repository drift stops without reporting success and removes any newly copied candidate. The external output
  path is canonicalized, rejected if it resolves into Git or traverses a reparse point, and created exclusively. Copying streams the
  inspected snapshot through a fresh SHA-256, requires exact digest agreement, fsyncs the new file and removes partial/drifted output.
  Regressions cover post-preflight drift, repository/reparse destinations, pre-existing output and copied-byte digest drift.
- Independent Release/Security rereview accepted immutable correction commit
  `2843fc9b7e37876fc236226587d4ae2abfa71ae7` with no remaining actionable finding. Reviewer independently ran 11 operator tests and
  `git diff --check`; external mutations were zero. The documented same-user/privileged atomic-swap residual remains outside this local
  Owner-operator threat boundary and does not weaken fail-closed handling of ordinary concurrent drift or accidental redirection.

- Before implementation, focused tests reproduced the mismatch: the inspector
  rejected `android-closed`, `APP_FLAVOR=production` remained accepted, and the
  Gradle contract had no release-channel input.
- `py -3.10 -m unittest tools.tests.test_mobile_release -v`: 22/22 passed,
  including genuine bundletool rejection of a JDK-signed placeholder ZIP, a
  stable-AAB snapshot mutation regression, four wrapper-component tamper
  regressions, private wrapper snapshot/minimal-environment checks, actual
  Gradle duplicate-key sentinel non-disclosure, the real temporary JDK
  keytool/jarsigner round trip, and appended unsigned-entry rejection.
- `py -3.10 -m unittest tools.tests.test_android_closed_testing -v`: 16/16
  passed after the hosted-step reorder.
- `py -3.10 -m unittest tools.tests.test_ci_workflow_contract -v`: 10 contract
  cases passed; the aggregate final-gate Git Bash process again exited with
  the known Windows `0xC0000142` environment failure before script evaluation,
  so that environment-dependent case is not claimed as passed.
- `python -m py_compile tools/mobile_release.py tools/tests/test_mobile_release.py`:
  passed.
- Black 24.4.2 formatter API and check semantics: passed for
  `tools/mobile_release.py` and `tools/tests/test_mobile_release.py`; the
  multi-file Windows CLI stalled as documented in the repository environment
  guide and was stopped before using the per-file API.
- `tools/Invoke-FlutterToolchain.ps1 status`: PASS for Flutter 3.47.0 / Dart
  3.13.0.
- Unconfigured fictional release build: failed before compilation exactly at
  missing `MOBILE_RELEASE_CHANNEL` after Gradle loaded the changed script.
- Fully configured fictional external-signer build: passed and produced a
  52.4 MB contract-test AAB. Strict inspection passed for 654 entries with
  package `tw.org.ntubtob.portal.contracttest`, API 36, channel
  `android-closed`, Basic scope, version transition `0 -> 1`, exact artifact
  SHA-256, and exact fictional signer SHA-256. The temporary keystore was
  removed; no real configuration, key, password, provider, endpoint, Console,
  cloud, device, production, upload, or rollout was accessed.
- The corrected strict CLI accepted a newly generated real fictional AAB after
  offline bundletool validation. Its manifest established package
  `tw.org.ntubtob.portal.contracttest`, version `0.1.0 (1)`, min SDK 24, and
  target/compile SDK 36; all reported hash/signature evidence came from the
  single private snapshot.
- Main independently reproduced the Windows path with deterministic UTF-8 JVM
  output. Offline bundletool validation, manifest parsing, archive contract,
  byte hash and fictional signer verification all passed against the same AAB;
  the tool keeps strict UTF-8 decoding instead of accepting locale-dependent
  replacement characters.
- `git diff --check`: passed (line-ending conversion warnings only).

## Hosted contract

The integrated workflow carries the following contract:

- `APP_FLAVOR=staging` replaces the rejected production flavor;
- Dart define `RELEASE_CHANNEL=android-closed` is explicit;
- the signed contract-test build supplies environment values
  `MOBILE_RELEASE_CHANNEL=android-closed`,
  `MOBILE_RELEASE_PREVIOUS_VERSION_CODE=0`,
  `MOBILE_RELEASE_STAGING_API_ORIGIN_SHA256=9e60f93f593ab35cc5e3ed1fa443c25a670f32e0342e5c1876f6ab29876c195c`,
  and
  `MOBILE_RELEASE_STAGING_PROVIDER_CONFIG_SHA256=47c660e43fc0a90f4c02fdf48584f10cb97137413c42e92ec926c652690c6ced`;
- inspector arguments include `--expected-previous-version-code 0`,
  `--expected-staging-api-origin-sha256` with the fictional digest above, and
  `--expected-staging-provider-config-sha256` with the fictional digest above;
- retain `--mode contract-test` for hosted fictional evidence. Real candidate
  inspection must use `--mode android-closed`.
- run the mobile release tooling tests after the signed fictional build so the
  pinned dependency set is already materialized, then run strict inspection;
  bundletool resolution remains `--offline`, with no download or upload.
- the checked-out tracked wrapper is never regenerated in CI; inspector
  invocation requires JDK 17 through `JAVA_HOME` and verifies all wrapper
  component digests before launching the private snapshot.

The two listed digests are derived only from the repository's pre-existing
reserved/fictional contract-test configuration. They are not candidate
configuration or authorization for external work.

## Remaining gates and limits

- This lane did not discover a real staging endpoint/provider tuple, Play
  package history, upload certificate, keystore, or password. Those values and
  their digests remain external exact approvals.
- Independent Release/Security acceptance and the single hosted gate remain required before merge. No real candidate may be derived
  before the accepted contract commit is merged.
- Store upload, Android 15 device validation, account/MFA, Play processing, and
  Closed Testing evidence remain later bounded phases of TASK-170.

## Android-owned changed paths

- `clients/flutter_app/android/app/build.gradle.kts`
- `clients/flutter_app/android/build.gradle.kts`
- `clients/flutter_app/android/.gitignore`
- `clients/flutter_app/android/gradlew`
- `clients/flutter_app/android/gradlew.bat`
- `clients/flutter_app/android/gradle/wrapper/gradle-wrapper.jar`
- `clients/flutter_app/README.md`
- `.github/workflows/flutter-tests.yml`
- `tools/mobile_release.py`
- `tools/tests/test_mobile_release.py`
- `docs/coordination/reports/TASK-170-ANDROID-CANDIDATE.md`

`clients/flutter_app/pubspec.yaml` was inspected but intentionally unchanged at `0.1.0+1`.
