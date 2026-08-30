# TASK-169 Android release writer report

## Delivered

- Android app and the pinned `flutter_line_sdk` compatibility override now
  explicitly compile against API 36; the app explicitly targets API 36.
- `release` Gradle tasks fail before compilation unless the approved package,
  pubspec version name/code, production/real/Basic-only Dart defines, HTTPS
  origin, distinct provider client IDs, and all external signing fields are
  present and consistent. Candidate mode rejects local/reserved endpoints,
  debug-shaped provider/signing identities, in-repository keystores, and the
  isolated contract-test identity.
- `pubspec.yaml` now carries the explicit initial build number
  `0.1.0+1`. No keystore, password, real provider ID, real endpoint, or store
  credential was added.
- Release builds embed a non-secret, sorted contract asset. The repository
  inspector validates canonical metadata, package/version markers, archive
  integrity and paths, absence of signing material, JAR signature structure,
  exact signer SHA-256, and strict JDK verification of every archive entry
  without accepting a signing password. The strict verifier trusts only a
  temporary copy of the already fingerprint-approved public certificate.
- Hosted Flutter CI retains the fake debug build, proves an unconfigured
  release fails, creates only an ephemeral visibly fictional signer outside
  the repository, builds the isolated `.contracttest` AAB with reserved values,
  and inspects it without upload or artifact retention. API 36 setup discovers
  only executable command-line tools inside the canonical `ANDROID_SDK_ROOT`,
  `ANDROID_HOME`, or standard hosted-runner SDK root, installs exactly the API
  36 platform, and fails if the tool or installed package cannot be verified.

## Verification

- `python -m unittest tools.tests.test_mobile_release -v`: 12/12 passed,
  including a real temporary JDK keytool/jarsigner round trip and rejection of
  an unsigned `classes2.dex` appended after signing.
- `python -m py_compile tools/mobile_release.py tools/tests/test_mobile_release.py`:
  passed.
- `python -m unittest tools.tests.test_ci_workflow_contract -v`: 10 contract
  cases passed; the Git Bash process used by the aggregate-script test exited
  with Windows `0xC0000142` before evaluating the script, so that one local
  environment-dependent case is not claimed as passed.
- Hosted run `33329539898`: every other selected job passed, but the Flutter
  job stopped at the pre-correction bare `sdkmanager` command with exit 127.
  This correction has repository tests only and has not been rerun hosted.
- `git diff --check`: passed (line-ending conversion warnings only).
- `python -m black --check ...`: not run because Black is not installed in the
  active Windows Python.

## Remaining gates and risk

- This host has no Flutter/Dart or Android SDK command available, so the new
  Kotlin DSL and signed contract-test AAB build/inspection require the pinned
  hosted Flutter gate. The corrected SDK discovery/install path also requires
  that rerun; passing repository tests do not substitute for hosted evidence.
- A future Closed Testing candidate still requires Owner-approved real HTTPS
  configuration, existing package/version decision, external signing material,
  signer fingerprint, Play Console access, real-device verification, and store
  approval. This task performed none of those actions and did not upload,
  publish, deploy, or contact a provider/backend.

## Android-owned changed paths

- `.github/workflows/flutter-tests.yml`
- `clients/flutter_app/android/app/build.gradle.kts`
- `clients/flutter_app/android/build.gradle.kts`
- `clients/flutter_app/pubspec.yaml`
- `tools/mobile_release.py`
- `tools/tests/test_mobile_release.py`
- `docs/coordination/reports/TASK-169-ANDROID.md`
