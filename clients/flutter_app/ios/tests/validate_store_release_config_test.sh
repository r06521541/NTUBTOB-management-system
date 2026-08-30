#!/bin/sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
validator="$script_dir/../validate_store_release_config.sh"
fixture_root="$(mktemp -d)"
trap 'rm -rf "$fixture_root"' EXIT HUP INT TERM
mkdir -p "$fixture_root/Flutter" "$fixture_root/Runner"
cp "$script_dir/../Flutter/StoreReleaseContract.xcconfig" \
  "$fixture_root/Flutter/StoreReleaseContract.xcconfig"
cp "$script_dir/../Runner/Runner.entitlements.example" \
  "$fixture_root/Runner/Runner.entitlements"

encode_defines() {
  result=''
  for pair in "$@"; do
    encoded="$(printf '%s' "$pair" | base64 | tr -d '\r\n')"
    if [ -n "$result" ]; then
      result="$result,$encoded"
    else
      result="$encoded"
    fi
  done
  printf '%s' "$result"
}

expect_status() {
  expected="$1"
  label="$2"
  shift 2
  set +e
  output="$(env "$@" /bin/sh "$validator" 2>&1)"
  actual="$?"
  set -e
  if [ "$actual" -ne "$expected" ]; then
    printf 'FAIL: %s (expected %s, got %s)\n%s\n' \
      "$label" "$expected" "$actual" "$output" >&2
    exit 1
  fi
}

fake_defines="$(encode_defines \
  APP_FLAVOR=development \
  CLIENT_MODE=fake \
  FLUTTER_SYSTEM_DEFINE=coexists)"
real_staging_defines="$(encode_defines \
  APP_FLAVOR=staging \
  CLIENT_MODE=real \
  API_BASE_URL=https://staging.invalid \
  LINE_CHANNEL_ID=1234567890 \
  GOOGLE_CLIENT_ID=123-ios.apps.googleusercontent.com \
  GOOGLE_SERVER_CLIENT_ID=456-web.apps.googleusercontent.com \
  FLUTTER_SYSTEM_DEFINE=coexists)"
real_production_defines="$(encode_defines \
  APP_FLAVOR=production \
  CLIENT_MODE=real \
  API_BASE_URL=https://production.invalid \
  LINE_CHANNEL_ID=1234567890 \
  GOOGLE_CLIENT_ID=123-ios.apps.googleusercontent.com \
  GOOGLE_SERVER_CLIENT_ID=456-web.apps.googleusercontent.com \
  FLUTTER_SYSTEM_DEFINE=coexists)"
ready_production_defines="$(encode_defines \
  APP_FLAVOR=production \
  CLIENT_MODE=real \
  API_BASE_URL=https://production.invalid \
  LINE_CHANNEL_ID=1234567890 \
  GOOGLE_CLIENT_ID=123-ios.apps.googleusercontent.com \
  GOOGLE_SERVER_CLIENT_ID=456-web.apps.googleusercontent.com \
  FLUTTER_SYSTEM_DEFINE=coexists \
  APPLE_SIGN_IN_RUNTIME_IMPLEMENTED=true)"

expect_status 0 'clean fake debug build' \
  SRCROOT="$fixture_root" \
  CONFIGURATION=Debug \
  DART_DEFINES="$fake_defines" \
  IOS_RELEASE_CONTRACT_VERSION=1 \
  APPLE_SIGN_IN_REPOSITORY_STATUS=not_implemented \
  IOS_DISTRIBUTION_CHANNEL= \
  IOS_EXTERNAL_SIGNING_READY=NO \
  DEVELOPMENT_TEAM= \
  PROVISIONING_PROFILE_SPECIFIER= \
  EXPANDED_CODE_SIGN_IDENTITY=

expect_status 0 'fake profile remains non-distribution' \
  SRCROOT="$fixture_root" \
  CONFIGURATION=Profile \
  DART_DEFINES="$fake_defines" \
  IOS_RELEASE_CONTRACT_VERSION=1 \
  APPLE_SIGN_IN_REPOSITORY_STATUS=not_implemented \
  IOS_DISTRIBUTION_CHANNEL= \
  IOS_EXTERNAL_SIGNING_READY=NO \
  DEVELOPMENT_TEAM= \
  PROVISIONING_PROFILE_SPECIFIER= \
  EXPANDED_CODE_SIGN_IDENTITY=

expect_status 0 'staging real debug remains non-distribution' \
  SRCROOT="$fixture_root" \
  CONFIGURATION=Debug \
  DART_DEFINES="$real_staging_defines" \
  IOS_RELEASE_CONTRACT_VERSION=1 \
  APPLE_SIGN_IN_REPOSITORY_STATUS=not_implemented \
  IOS_DISTRIBUTION_CHANNEL= \
  IOS_EXTERNAL_SIGNING_READY=NO

expect_status 0 'staging profile remains non-distribution' \
  SRCROOT="$fixture_root" \
  CONFIGURATION=Profile \
  DART_DEFINES="$real_staging_defines" \
  IOS_RELEASE_CONTRACT_VERSION=1 \
  APPLE_SIGN_IN_REPOSITORY_STATUS=not_implemented \
  IOS_DISTRIBUTION_CHANNEL= \
  IOS_EXTERNAL_SIGNING_READY=NO

expect_status 2 'staging debug cannot claim TestFlight distribution' \
  SRCROOT="$fixture_root" \
  CONFIGURATION=Debug \
  DART_DEFINES="$real_staging_defines" \
  IOS_RELEASE_CONTRACT_VERSION=1 \
  APPLE_SIGN_IN_REPOSITORY_STATUS=not_implemented \
  IOS_DISTRIBUTION_CHANNEL=testflight \
  IOS_EXTERNAL_SIGNING_READY=YES

common_release_env="SRCROOT=$fixture_root CONFIGURATION=Release IOS_RELEASE_CONTRACT_VERSION=1 IOS_EXTERNAL_SIGNING_READY=YES CODE_SIGNING_ALLOWED=YES DEVELOPMENT_TEAM=FICTIONALTEAM PROVISIONING_PROFILE_SPECIFIER=FICTIONAL_TESTFLIGHT_PROFILE EXPANDED_CODE_SIGN_IDENTITY=FICTIONAL_DISTRIBUTION_IDENTITY PRODUCT_BUNDLE_IDENTIFIER=invalid.review.mobile FLUTTER_BUILD_NAME=1.2.3 FLUTTER_BUILD_NUMBER=456 APPLE_SIGN_IN_REPOSITORY_STATUS=not_implemented"

# shellcheck disable=SC2086
expect_status 0 'staging TestFlight contract' \
  $common_release_env \
  DART_DEFINES="$real_staging_defines" \
  IOS_DISTRIBUTION_CHANNEL=testflight

# A complete scan must reject trailing conflicting or malformed entries rather
# than returning the first matching release-critical definition.
# shellcheck disable=SC2086
expect_status 2 'duplicate flavor definition is rejected' \
  $common_release_env \
  DART_DEFINES="$real_staging_defines,$(encode_defines APP_FLAVOR=staging)" \
  IOS_DISTRIBUTION_CHANNEL=testflight

# shellcheck disable=SC2086
expect_status 2 'later mixed development definitions are rejected' \
  $common_release_env \
  DART_DEFINES="$real_staging_defines,$(encode_defines APP_FLAVOR=development CLIENT_MODE=fake)" \
  IOS_DISTRIBUTION_CHANNEL=testflight

# shellcheck disable=SC2086
expect_status 2 'duplicate auth definition is rejected' \
  $common_release_env \
  DART_DEFINES="$real_staging_defines,$(encode_defines GOOGLE_CLIENT_ID=999-other.apps.googleusercontent.com)" \
  IOS_DISTRIBUTION_CHANNEL=testflight

# shellcheck disable=SC2086
expect_status 2 'malformed base64 entry is rejected' \
  $common_release_env \
  DART_DEFINES="$real_staging_defines,not-base64!" \
  IOS_DISTRIBUTION_CHANNEL=testflight

# shellcheck disable=SC2086
expect_status 2 'malformed decoded entry is rejected' \
  $common_release_env \
  DART_DEFINES="$real_staging_defines,$(encode_defines SYSTEM_DEFINE_WITHOUT_EQUALS)" \
  IOS_DISTRIBUTION_CHANNEL=testflight

expect_status 2 'fake mode rejects unexpected service definition' \
  SRCROOT="$fixture_root" \
  CONFIGURATION=Debug \
  DART_DEFINES="$fake_defines,$(encode_defines API_BASE_URL=https://unexpected.invalid)" \
  IOS_RELEASE_CONTRACT_VERSION=1 \
  APPLE_SIGN_IN_REPOSITORY_STATUS=not_implemented \
  IOS_DISTRIBUTION_CHANNEL= \
  IOS_EXTERNAL_SIGNING_READY=NO \
  DEVELOPMENT_TEAM= \
  PROVISIONING_PROFILE_SPECIFIER= \
  EXPANDED_CODE_SIGN_IDENTITY=

# shellcheck disable=SC2086
expect_status 2 'missing distribution channel' \
  $common_release_env \
  DART_DEFINES="$real_staging_defines"

# shellcheck disable=SC2086
expect_status 2 'staging cannot claim App Store release' \
  $common_release_env \
  DART_DEFINES="$real_staging_defines" \
  IOS_DISTRIBUTION_CHANNEL=app-store

# shellcheck disable=SC2086
expect_status 2 'signing must be explicitly external' \
  SRCROOT="$fixture_root" \
  CONFIGURATION=Release \
  DART_DEFINES="$real_staging_defines" \
  IOS_RELEASE_CONTRACT_VERSION=1 \
  IOS_DISTRIBUTION_CHANNEL=testflight \
  IOS_EXTERNAL_SIGNING_READY=NO \
  CODE_SIGNING_ALLOWED=YES \
  DEVELOPMENT_TEAM=FICTIONALTEAM \
  PROVISIONING_PROFILE_SPECIFIER=FICTIONAL_TESTFLIGHT_PROFILE \
  EXPANDED_CODE_SIGN_IDENTITY=FICTIONAL_DISTRIBUTION_IDENTITY \
  PRODUCT_BUNDLE_IDENTIFIER=invalid.review.mobile \
  FLUTTER_BUILD_NAME=1.2.3 \
  FLUTTER_BUILD_NUMBER=456 \
  APPLE_SIGN_IN_REPOSITORY_STATUS=not_implemented

# shellcheck disable=SC2086
expect_status 2 'debug-shaped bundle identity is rejected' \
  $common_release_env \
  DART_DEFINES="$real_staging_defines" \
  IOS_DISTRIBUTION_CHANNEL=testflight \
  PRODUCT_BUNDLE_IDENTIFIER=invalid.debug.mobile

# The committed repository marker keeps public iOS release blocked until a
# future Apple-login implementation also supplies entitlement/provider gates.
# shellcheck disable=SC2086
expect_status 2 'production remains blocked without Apple implementation' \
  $common_release_env \
  DART_DEFINES="$real_production_defines" \
  IOS_DISTRIBUTION_CHANNEL=app-store

expect_status 2 'private build settings cannot override repository readiness' \
  SRCROOT="$fixture_root" \
  CONFIGURATION=Release \
  DART_DEFINES="$ready_production_defines" \
  IOS_RELEASE_CONTRACT_VERSION=1 \
  IOS_DISTRIBUTION_CHANNEL=app-store \
  IOS_EXTERNAL_SIGNING_READY=YES \
  CODE_SIGNING_ALLOWED=YES \
  DEVELOPMENT_TEAM=FICTIONALTEAM \
  PROVISIONING_PROFILE_SPECIFIER=FICTIONAL_APP_STORE_PROFILE \
  EXPANDED_CODE_SIGN_IDENTITY=FICTIONAL_DISTRIBUTION_IDENTITY \
  PRODUCT_BUNDLE_IDENTIFIER=invalid.review.mobile \
  FLUTTER_BUILD_NAME=1.2.3 \
  FLUTTER_BUILD_NUMBER=456 \
  APPLE_SIGN_IN_REPOSITORY_STATUS=ready \
  APPLE_PROVIDER_CONFIGURED_EXTERNALLY=YES \
  CODE_SIGN_ENTITLEMENTS=Runner/Runner.entitlements

sed -i \
  's/APPLE_SIGN_IN_REPOSITORY_STATUS=not_implemented/APPLE_SIGN_IN_REPOSITORY_STATUS=ready/' \
  "$fixture_root/Flutter/StoreReleaseContract.xcconfig"

expect_status 2 'repository readiness cannot replace runtime implementation' \
  SRCROOT="$fixture_root" \
  CONFIGURATION=Release \
  DART_DEFINES="$real_production_defines" \
  IOS_RELEASE_CONTRACT_VERSION=1 \
  IOS_DISTRIBUTION_CHANNEL=app-store \
  IOS_EXTERNAL_SIGNING_READY=YES \
  CODE_SIGNING_ALLOWED=YES \
  DEVELOPMENT_TEAM=FICTIONALTEAM \
  PROVISIONING_PROFILE_SPECIFIER=FICTIONAL_APP_STORE_PROFILE \
  EXPANDED_CODE_SIGN_IDENTITY=FICTIONAL_DISTRIBUTION_IDENTITY \
  PRODUCT_BUNDLE_IDENTIFIER=invalid.review.mobile \
  FLUTTER_BUILD_NAME=1.2.3 \
  FLUTTER_BUILD_NUMBER=456 \
  APPLE_SIGN_IN_REPOSITORY_STATUS=ready \
  APPLE_PROVIDER_CONFIGURED_EXTERNALLY=YES \
  CODE_SIGN_ENTITLEMENTS=Runner/Runner.entitlements

printf '%s\n' \
  '<?xml version="1.0" encoding="UTF-8"?>' \
  '<plist version="1.0">' \
  '<dict>' \
  '<key>com.apple.developer.applesignin</key>' \
  '<array><string>Primary</string></array>' \
  '<key>unrelated.capability</key>' \
  '<array><string>Default</string></array>' \
  '</dict>' \
  '</plist>' > "$fixture_root/Runner/Runner.entitlements"

expect_status 2 'Apple Default must belong to the required entitlement key' \
  SRCROOT="$fixture_root" \
  CONFIGURATION=Release \
  DART_DEFINES="$ready_production_defines" \
  IOS_RELEASE_CONTRACT_VERSION=1 \
  IOS_DISTRIBUTION_CHANNEL=app-store \
  IOS_EXTERNAL_SIGNING_READY=YES \
  CODE_SIGNING_ALLOWED=YES \
  DEVELOPMENT_TEAM=FICTIONALTEAM \
  PROVISIONING_PROFILE_SPECIFIER=FICTIONAL_APP_STORE_PROFILE \
  EXPANDED_CODE_SIGN_IDENTITY=FICTIONAL_DISTRIBUTION_IDENTITY \
  PRODUCT_BUNDLE_IDENTIFIER=invalid.review.mobile \
  FLUTTER_BUILD_NAME=1.2.3 \
  FLUTTER_BUILD_NUMBER=456 \
  APPLE_SIGN_IN_REPOSITORY_STATUS=ready \
  APPLE_PROVIDER_CONFIGURED_EXTERNALLY=YES \
  CODE_SIGN_ENTITLEMENTS=Runner/Runner.entitlements

cp "$script_dir/../Runner/Runner.entitlements.example" \
  "$fixture_root/Runner/Runner.entitlements"

expect_status 0 'future complete fictional Apple contract vector' \
  SRCROOT="$fixture_root" \
  CONFIGURATION=Release \
  DART_DEFINES="$ready_production_defines" \
  IOS_RELEASE_CONTRACT_VERSION=1 \
  IOS_DISTRIBUTION_CHANNEL=app-store \
  IOS_EXTERNAL_SIGNING_READY=YES \
  CODE_SIGNING_ALLOWED=YES \
  DEVELOPMENT_TEAM=FICTIONALTEAM \
  PROVISIONING_PROFILE_SPECIFIER=FICTIONAL_APP_STORE_PROFILE \
  EXPANDED_CODE_SIGN_IDENTITY=FICTIONAL_DISTRIBUTION_IDENTITY \
  PRODUCT_BUNDLE_IDENTIFIER=invalid.review.mobile \
  FLUTTER_BUILD_NAME=1.2.3 \
  FLUTTER_BUILD_NUMBER=456 \
  APPLE_SIGN_IN_REPOSITORY_STATUS=ready \
  APPLE_PROVIDER_CONFIGURED_EXTERNALLY=YES \
  CODE_SIGN_ENTITLEMENTS=Runner/Runner.entitlements

printf 'validate_store_release_config: all contract cases passed\n'
