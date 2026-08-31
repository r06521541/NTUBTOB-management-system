# TASK-170 Android candidate contract writer report

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

## Regression and verification

- Before implementation, focused tests reproduced the mismatch: the inspector
  rejected `android-closed`, `APP_FLAVOR=production` remained accepted, and the
  Gradle contract had no release-channel input.
- `py -3.10 -m unittest tools.tests.test_mobile_release -v`: 18/18 passed,
  including genuine bundletool rejection of a JDK-signed placeholder ZIP, a
  stable-snapshot mutation regression, the real temporary JDK
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

The two listed digests are derived only from the repository's pre-existing
reserved/fictional contract-test configuration. They are not candidate
configuration or authorization for external work.

## Remaining gates and limits

- This lane did not discover a real staging endpoint/provider tuple, Play
  package history, upload certificate, keystore, or password. Those values and
  their digests remain external exact approvals.
- Main still owns workflow reconciliation, combined-diff review, full affected
  Flutter/analyze verification, independent Release/Security acceptance, and
  the single hosted gate. No real candidate may be derived before the accepted
  contract commit is merged.
- Store upload, Android 15 device validation, account/MFA, Play processing, and
  Closed Testing evidence remain later bounded phases of TASK-170.

## Android-owned changed paths

- `clients/flutter_app/android/app/build.gradle.kts`
- `clients/flutter_app/android/build.gradle.kts`
- `clients/flutter_app/README.md`
- `.github/workflows/flutter-tests.yml`
- `tools/mobile_release.py`
- `tools/tests/test_mobile_release.py`
- `docs/coordination/reports/TASK-170-ANDROID-CANDIDATE.md`

`clients/flutter_app/pubspec.yaml` was inspected but intentionally unchanged at
`0.1.0+1`; no commit or push was made by this writer.
