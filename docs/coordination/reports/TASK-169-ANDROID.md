# TASK-169 Android release writer report

## Delivered

- Android app and the pinned `flutter_line_sdk` compatibility override now
  explicitly compile against API 36; the app explicitly targets API 36.
- `release` Gradle tasks fail before compilation unless the approved package,
  pubspec version name/code, production/real/Basic-only Dart defines, HTTPS
  origin, distinct provider client IDs, and all external signing fields are
  present and consistent. The two Flutter 3.47.0-owned build identity defines
  and exact six version metadata defines are accepted and validated separately;
  missing or additional defines still fail closed. Candidate mode rejects
  local/reserved endpoints,
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
  The generated asset is registered through the AGP 9.1 Variant Sources API,
  which supplies the generator-to-asset merge task dependency automatically.
- Hosted Flutter CI retains the fake debug build, proves an unconfigured
  release fails, creates only an ephemeral visibly fictional signer outside
  the repository, builds the isolated `.contracttest` AAB with reserved values,
  and inspects it without upload or artifact retention. API 36 setup discovers
  only executable command-line tools inside the canonical `ANDROID_SDK_ROOT`,
  `ANDROID_HOME`, or standard hosted-runner SDK root, installs exactly the API
  36 platform, and fails if the tool or installed package cannot be verified.

## Verification

- `python -m unittest tools.tests.test_mobile_release -v`: 14/14 passed,
  including a real temporary JDK keytool/jarsigner round trip and rejection of
  an unsigned `classes2.dex` appended after signing, plus the pinned Flutter
  metadata define and generated asset registration contracts.
- `python -m py_compile tools/mobile_release.py tools/tests/test_mobile_release.py`:
  passed.
- `python -m unittest tools.tests.test_ci_workflow_contract -v`: 10 contract
  cases passed; the Git Bash process used by the aggregate-script test exited
  with Windows `0xC0000142` before evaluating the script, so that one local
  environment-dependent case is not claimed as passed.
- Hosted run `33331387388` at immutable SHA
  `ab07b665a3812d59459e04df6792432930e3bd43`: every selected gate passed,
  including API 36 installation, Flutter format/analyze/tests, the unconfigured
  release fail-closed proof, ephemeral fictional signer creation, signed
  contract-test AAB build and strict artifact inspection.
- `git diff --check`: passed (line-ending conversion warnings only).
- `python -m black --check ...`: not run because Black is not installed in the
  active Windows Python.

## Remaining gates and risk

- Windows local evidence did not execute Flutter/Android, but the pinned hosted
  runner supplied the required API 36 Gradle/AAB and inspection evidence above.
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
