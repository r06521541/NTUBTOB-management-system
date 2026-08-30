#!/bin/sh
set -eu

fail() {
  printf 'error: %s\n' "$1" >&2
  exit 2
}

decode_define() {
  encoded="$1"
  if /usr/bin/base64 --help 2>&1 | grep -q -- '--decode'; then
    printf '%s' "$encoded" | /usr/bin/base64 --decode
  else
    printf '%s' "$encoded" | /usr/bin/base64 -D
  fi
}

dart_define() {
  requested="$1"
  old_ifs="$IFS"
  IFS=,
  for encoded in ${DART_DEFINES:-}; do
    decoded="$(decode_define "$encoded")" || continue
    case "$decoded" in
      "$requested="*) printf '%s' "${decoded#*=}"; IFS="$old_ifs"; return 0 ;;
    esac
  done
  IFS="$old_ifs"
}

require_external_value() {
  label="$1"
  value="$2"
  case "$value" in
    ''|'-'|*'$('*|*')'*) fail "$label must be supplied by the external signing environment" ;;
  esac
}

app_flavor="$(dart_define APP_FLAVOR)"
client_mode="$(dart_define CLIENT_MODE)"
apple_runtime_implemented="$(dart_define APPLE_SIGN_IN_RUNTIME_IMPLEMENTED)"
configuration="${CONFIGURATION:-}"
distribution_channel="${IOS_DISTRIBUTION_CHANNEL:-}"
contract_file="${SRCROOT:-}/Flutter/StoreReleaseContract.xcconfig"
[ -f "$contract_file" ] || \
  fail 'repository-owned iOS release contract file is missing'
contract_version="$(sed -n 's/^IOS_RELEASE_CONTRACT_VERSION=//p' "$contract_file")"
repository_status="$(sed -n 's/^APPLE_SIGN_IN_REPOSITORY_STATUS=//p' "$contract_file")"
non_distribution_configuration=false
case "$configuration" in
  Debug|Profile) non_distribution_configuration=true ;;
esac

[ "$contract_version" = 1 ] || \
  fail 'repository-owned iOS release contract version is missing or unsupported'
[ "${IOS_RELEASE_CONTRACT_VERSION:-}" = "$contract_version" ] || \
  fail 'resolved iOS release contract version does not match repository source'

case "$repository_status" in
  not_implemented|ready) ;;
  *) fail 'repository-owned Sign in with Apple status is missing or invalid' ;;
esac
[ "${APPLE_SIGN_IN_REPOSITORY_STATUS:-}" = "$repository_status" ] || \
  fail 'resolved Sign in with Apple status does not match repository source'

if [ "$app_flavor" = development ] && [ "$client_mode" = fake ]; then
  [ "$non_distribution_configuration" = true ] || \
    fail 'development fake iOS builds must use a non-distribution configuration'
  [ -z "$distribution_channel" ] || \
    fail 'development fake iOS builds must not select a distribution channel'
  [ "${IOS_EXTERNAL_SIGNING_READY:-NO}" != YES ] || \
    fail 'development fake iOS builds must not claim release signing readiness'
  [ -z "${DEVELOPMENT_TEAM:-}" ] || \
    fail 'development fake iOS builds must not receive a signing team'
  [ -z "${PROVISIONING_PROFILE_SPECIFIER:-}" ] || \
    fail 'development fake iOS builds must not receive a provisioning profile'
  [ -z "${EXPANDED_CODE_SIGN_IDENTITY:-}" ] || \
    fail 'development fake iOS builds must not receive a signing identity'
  exit 0
fi

if [ "$app_flavor" = staging ] && [ "$client_mode" = real ] && \
    [ "$non_distribution_configuration" = true ]; then
  [ -z "$distribution_channel" ] || \
    fail 'non-distribution staging builds must not select a distribution channel'
  [ "${IOS_EXTERNAL_SIGNING_READY:-NO}" != YES ] || \
    fail 'non-distribution staging builds must not claim release signing readiness'
  exit 0
fi

if { [ "$app_flavor" != staging ] && [ "$app_flavor" != production ]; } || \
    [ "$client_mode" != real ]; then
  fail 'iOS release build flavor/client mode is missing, mixed, or invalid'
fi
[ "$configuration" = Release ] || \
  fail 'TestFlight and App Store candidates must use the Release configuration'

case "$app_flavor:$distribution_channel" in
  staging:testflight|production:app-store) ;;
  *) fail 'iOS flavor and distribution channel are missing or mixed' ;;
esac

[ "${IOS_EXTERNAL_SIGNING_READY:-}" = YES ] || \
  fail 'iOS distribution signing must be explicitly supplied outside the repository'
[ "${CODE_SIGNING_ALLOWED:-}" = YES ] || \
  fail 'code signing is disabled for this distribution candidate'
require_external_value DEVELOPMENT_TEAM "${DEVELOPMENT_TEAM:-}"
require_external_value PROVISIONING_PROFILE_SPECIFIER \
  "${PROVISIONING_PROFILE_SPECIFIER:-}"
require_external_value EXPANDED_CODE_SIGN_IDENTITY \
  "${EXPANDED_CODE_SIGN_IDENTITY:-}"

bundle_id="${PRODUCT_BUNDLE_IDENTIFIER:-}"
printf '%s\n' "$bundle_id" | \
  grep -Eq '^[A-Za-z0-9][A-Za-z0-9-]*(\.[A-Za-z0-9][A-Za-z0-9-]*){2,}$' || \
  fail 'iOS bundle identity is missing, unresolved, or malformed'
if printf '%s\n' "$bundle_id" | tr '[:upper:]' '[:lower:]' | \
    grep -Eq '(^|[.-])(debug|test|example|dev)([.-]|$)'; then
  fail 'iOS distribution bundle identity is debug/test-shaped'
fi

printf '%s\n' "${FLUTTER_BUILD_NAME:-}" | \
  grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || \
  fail 'FLUTTER_BUILD_NAME must be an explicit three-part numeric version'
printf '%s\n' "${FLUTTER_BUILD_NUMBER:-}" | grep -Eq '^[1-9][0-9]*$' || \
  fail 'FLUTTER_BUILD_NUMBER must be an explicit positive integer'

if [ "$app_flavor" = staging ]; then
  exit 0
fi

[ "$repository_status" = ready ] || \
  fail 'public iOS release is blocked: Sign in with Apple is not implemented'
[ "$apple_runtime_implemented" = true ] || \
  fail 'public iOS release is blocked: Apple runtime implementation marker is absent'
[ "${APPLE_PROVIDER_CONFIGURED_EXTERNALLY:-}" = YES ] || \
  fail 'public iOS release is blocked: Apple provider readiness is not externally confirmed'
[ "${CODE_SIGN_ENTITLEMENTS:-}" = Runner/Runner.entitlements ] || \
  fail 'public iOS release must bind the reviewed Apple sign-in entitlements file'
entitlements="${SRCROOT:-}/Runner/Runner.entitlements"
[ -f "$entitlements" ] || \
  fail 'public iOS release is missing the reviewed Apple sign-in entitlements file'
grep -Fq '<key>com.apple.developer.applesignin</key>' "$entitlements" || \
  fail 'public iOS release is missing the Sign in with Apple entitlement'
grep -Fq '<string>Default</string>' "$entitlements" || \
  fail 'public iOS release has an invalid Sign in with Apple entitlement mode'
