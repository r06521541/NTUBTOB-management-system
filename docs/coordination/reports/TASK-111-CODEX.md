# TASK-111 Codex implementation report

## Execution checkpoint and scope

- Goal: replace generated fictional release identity with the stable Owner-approved identity and add a reproducible hosted Flutter gate.
- Core files: Flutter package/runners/README, one reusable Flutter workflow, minimal classifier/final-gate integration, authorized CI contract files, and this report.
- Invariants: development remains explicitly fake; no endpoint, channel ID, Secret, signing credential, deployment, or real LINE/API call; existing Python/security gates remain required.
- Minimum evidence: identity/static scans, classifier/workflow contracts, pub/format/analyze/all tests, fake APK, merged manifest/APK/signing review, diff/scope/security checks.
- Deferred: hosted run/PR, real LINE/API configuration, iOS runtime/signing, release signing, deployment, TestFlight/store distribution.

Work began clean on branch `codex/task-111-flutter-release-identity` at `0c43adcc61559f7147d36d9d9b045606f0a9ecd7`. Main Work approved Topology A and explicitly expanded the writer boundary only to `tools/ci_change_classifier.py`, `tools/tests/test_ci_change_classifier.py`, and `tools/tests/test_ci_workflow_contract.py` for this integration.

## Delivered identity

- User-facing Android and iOS display name: `臺大校友比賽報你知`.
- Android namespace/application ID and relocated `MainActivity` package: `tw.org.ntubtob.portal`.
- iOS application bundle ID: `tw.org.ntubtob.portal`; test target IDs: `tw.org.ntubtob.portal.RunnerTests`, derived and non-colliding.
- Internal Dart package/project name: `ntubtob_portal`; all package imports and the explicit reproduction command were updated.
- Preserved boundaries: Android minSdk 24, main INTERNET permission, backup disabled, no release signing configuration; iOS target 15 and identifier-derived `line3rdp.$(PRODUCT_BUNDLE_IDENTIFIER)` callback; no development team, provisioning profile, certificate, keystore, channel ID, or endpoint value.
- Development composition remains explicit and fictional: `APP_FLAVOR=development` plus `CLIENT_MODE=fake`.

## Hosted CI topology

- `.github/workflows/flutter-tests.yml` is reusable only (`workflow_call`) and has no standalone push/pull-request trigger. It grants only `contents: read`.
- The reusable job pins Flutter exactly to stable `3.47.0`, resolves locked dependencies, checks Dart formatting, analyzes, runs all Flutter tests, and builds only a fake development debug APK. It does not upload or distribute the APK.
- The existing classifier selects `flutter` only for `clients/flutter_app/**` and `.github/workflows/flutter-tests.yml`; existing workflow/classifier contract changes remain conservative `full`. Full classification requires Flutter.
- `python-tests.yml` conditionally calls the reusable workflow for Flutter/full changes. Existing `CI final gate` now includes the Flutter job in `needs`, scope/result validation, and fail-closed aggregation. Failure, cancellation, or skip fails when selected/full; skip is legal only when classifier says Flutter is irrelevant. The required check remains the existing `CI final gate`; no branch-protection change was made or claimed.

### Action provenance

- `actions/checkout` official upstream `https://github.com/actions/checkout`: tag `v7.0.1` resolved by read-only `git ls-remote` to full SHA `3d3c42e5aac5ba805825da76410c181273ba90b1`. No optional input is needed in the reusable Flutter workflow.
- `subosito/flutter-action` upstream `https://github.com/subosito/flutter-action`: release/tag `v2.23.0` resolved by read-only `git ls-remote` to full SHA `1a449444c387b1966244ae4d4f8c696479add0b2`. Its official README/action metadata document `channel`, `flutter-version`, `cache`, and `pub-cache`; the workflow uses only those inputs.
- Both third-party actions are pinned by full commit SHA. No path-filter or artifact-upload action was introduced.

## Local verification

- `flutter pub get`: passed; existing exact dependency lock retained.
- `dart format --output=none --set-exit-if-changed .`: passed, 7 files and 0 changes after applying formatter output to renamed imports.
- `flutter analyze`: passed, no issues.
- `flutter test`: passed, all 71 tests.
- `flutter build apk --debug --dart-define=APP_FLAVOR=development --dart-define=CLIENT_MODE=fake`: passed with Flutter 3.47.0/Dart 3.13.0 and the TASK-107 Android/JDK toolchain.
- Fake debug APK (ignored and not committed): 163,365,346 bytes; SHA-256 `C4A6D4ABD6427C4CCFE01DF3AD839AFB7CD49D20E8573314BAA99D33071F66DD`.
- APK/merged manifest: package `tw.org.ntubtob.portal`, label `臺大校友比賽報你知`, minSdk 24, INTERNET present, `allowBackup=false`, `fullBackupContent=false`, debug-only `debuggable=true`. `apksigner verify --print-certs` passed and showed only `CN=Android Debug`.
- `python -m unittest tools.tests.test_ci_change_classifier tools.tests.test_ci_workflow_contract -v`: passed, 27 tests. Coverage locks Flutter/full/non-relevant classification, workflow-call-only topology, exact/fake commands, full-SHA actions, and final-gate fail/cancel/skip behavior.
- `python -m black --check` on the three authorized classifier/contract files: passed.
- Repository identity scan found no active `ntubtob_fictional_client`, `com.example.ntubtob`, or old iOS example bundle identity under `clients/flutter_app/**`.
- Secret/config scan found no credential, private-key, bearer-token, numeric LINE channel value, or service endpoint. URL review found only official action provenance, package/documentation/XML namespaces, and explicit `example.invalid` tests.
- Workflow action scan found only full-SHA third-party pins plus the reviewed local reusable-workflow call. `git diff --check` and cumulative changed-file boundary review passed.

## Limitations and side effects

- Hosted evidence is not yet available. Per task process, no PR was created; Domain review must notify Main Work before any Draft/ready PR for hosted evidence.
- The bundled local Python runtime has no PyYAML, so no separate local YAML parser was run. The repository's 27 static/executable classifier and workflow contract tests passed; GitHub's hosted parser remains part of deferred hosted evidence.
- No real LINE/API request, endpoint/channel/Secret access, backend/schema/database operation, external message, artifact upload, branch-protection mutation, deployment, PR, merge, release signing, TestFlight, or store action occurred.
- iOS runtime/build remains deferred to macOS/Xcode. Static project review is the available iOS evidence.
- The exact required `flutter_line_sdk 2.7.2` still emits its known forward-looking legacy Kotlin plugin warning; analyze, tests, and the fake debug build pass.
- External reads were limited to official action upstream documentation/tag refs and normal dependency/tool cache use. A single exact Git safe-directory entry was added for this task worktree because its creator SID differs from the execution SID; cleanup is `git config --global --unset-all safe.directory C:/Users/USER/Repos/NTUBTOB-management-system-flutter-task111` after the worktree is retired.
