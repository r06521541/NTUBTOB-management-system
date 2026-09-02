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
- Hosted run `33597055753` passed the workflow and non-iOS gates but failed the
  macOS compile because the app target was below the LINE SDK's iOS 15 minimum.
  The aligned target setting and regression are pending hosted revalidation.

## Remaining external limits

- Apple Developer enrollment、provider capability、signing、archive、TestFlight upload、real-device與production均未授權或執行。
