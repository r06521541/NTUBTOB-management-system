# TASK-178 implementation report

## Outcome

- Added a staging-only, Release, no-codesign TestFlight compile contract that
  rejects production, provider-ready, signing-ready, signing metadata,
  entitlements, debug configuration, unknown mode and bundle-identity drift.
- Added a hosted macOS/Xcode job that compiles the real-client iOS source and
  native Apple authorization bridge with fictional provider values, verifies
  the exact bundle identity and proves the output is unsigned.
- Actual TestFlight/App Store candidate validation remains unchanged and
  fail-closed. The public Apple repository marker remains `not_implemented`.
- The first hosted Xcode compile exposed that the Runner target inherited an
  iOS 13 default even though the project and current LINE SDK require iOS 15.
  Debug, Release and Profile now explicitly require iOS 15 at both levels.
- A second hosted run proved the remaining iOS 13 declaration came from
  `flutter_line_sdk` 2.7.2's Swift package. The dependency is upgraded to the
  official 3.0.0 release, whose package requires iOS 15 and Flutter 3.44+.
  Because that release is not yet available from pub.dev, the dependency uses
  its immutable official commit rather than a floating tag; comparison of the
  official tags shows no plugin Dart-library changes.

## Verification

- `ios/tests/validate_store_release_config_test.sh`: passed with exit 0 under
  Git Bash; the local tool emitted no captured stdout.
- `flutter test --no-pub test/apple_auth_test.dart test/integration_test.dart
  test/support_app_info_test.dart`: 72 passed.
- `flutter analyze --no-pub lib/integration.dart lib/basic_app.dart
  lib/support_app_info.dart test/apple_auth_test.dart test/integration_test.dart
  test/support_app_info_test.dart`: no issues.
- `git diff --check`: passed; Windows emitted only expected LF-to-CRLF checkout
  warnings.
- Initial hosted Quick repository gate exposed the previous one-job/two-action
  Flutter workflow assumption. The workflow contract now names and verifies the
  macOS job, four pinned actions, no-codesign/provider-off settings, unsigned
  check, exact bundle identity, and absence of artifact upload.
- `py -3.10 -m unittest discover -s tools/tests -p "test_ci_*.py" -v`:
  32 passed with one expected local Bash-environment skip.
- After the official LINE plugin upgrade, `flutter test --no-pub`: 316 passed;
  `flutter analyze --no-pub`: no issues.
- The three directly affected Python contract tests passed. The complete local
  `tools.tests.test_mobile_release` run had 21 passes and three pre-existing
  environment-only failures because the bounded bundletool runtime is not
  installed locally; the preceding hosted run executed those same bundletool
  checks and its only failure was the corrected workflow count assertion.
- Hosted run `33597055753` passed the workflow and non-iOS gates but failed the
  macOS compile because the app target was below the LINE SDK's iOS 15 minimum.
- Hosted run `33598316597` confirmed the target fix alone was insufficient:
  the plugin Swift package still declared iOS 13. Its Android job also exposed
  an obsolete workflow-wide staging-define count; that assertion is now scoped
  to the Android job. Both corrections remain pending hosted revalidation.

## Remaining external limits

- Apple Developer enrollment、provider capability、signing、archive、TestFlight upload、real-device與production均未授權或執行。
