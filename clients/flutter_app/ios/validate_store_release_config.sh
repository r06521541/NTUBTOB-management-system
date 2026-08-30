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

app_flavor=''
client_mode=''
api_base_url=''
line_channel_id=''
google_client_id=''
google_server_client_id=''
apple_runtime_implemented=''
app_flavor_seen=false
client_mode_seen=false
api_base_url_seen=false
line_channel_id_seen=false
google_client_id_seen=false
google_server_client_id_seen=false
apple_runtime_implemented_seen=false

scan_dart_defines() {
  raw_defines="${DART_DEFINES:-}"
  case "$raw_defines" in
    ''|,*|*,|*,,*) fail 'DART_DEFINES is missing or contains an empty entry' ;;
  esac

  old_ifs="$IFS"
  IFS=,
  # Encoded entries use only the base64 alphabet, so pathname expansion cannot
  # alter this intentional comma split.
  set -- $raw_defines
  IFS="$old_ifs"

  newline='
'
  carriage_return="$(printf '\r')"
  for encoded in "$@"; do
    printf '%s\n' "$encoded" | grep -Eq '^[A-Za-z0-9+/]+={0,2}$' || \
      fail 'DART_DEFINES contains malformed base64'
    [ $((${#encoded} % 4)) -eq 0 ] || \
      fail 'DART_DEFINES contains malformed base64 length'
    framed="$(decode_define "$encoded" && printf '__DART_DEFINE_END__')" || \
      fail 'DART_DEFINES contains undecodable base64'
    decoded="${framed%__DART_DEFINE_END__}"
    canonical="$(printf '%s' "$decoded" | /usr/bin/base64 | tr -d '\r\n')"
    [ "$canonical" = "$encoded" ] || \
      fail 'DART_DEFINES contains non-canonical or binary data'
    case "$decoded" in
      *"$newline"*|*"$carriage_return"*) \
        fail 'DART_DEFINES contains a multi-line decoded entry' ;;
      *=*) ;;
      *) fail 'DART_DEFINES contains a decoded entry without key/value syntax' ;;
    esac
    if printf '%s' "$decoded" | LC_ALL=C grep -q '[[:cntrl:]]'; then
      fail 'DART_DEFINES contains decoded control characters'
    fi
    key="${decoded%%=*}"
    value="${decoded#*=}"
    printf '%s\n' "$key" | grep -Eq '^[A-Za-z_][A-Za-z0-9_.-]*$' || \
      fail 'DART_DEFINES contains an invalid decoded key'

    case "$key" in
      APP_FLAVOR)
        [ "$app_flavor_seen" = false ] || \
          fail 'DART_DEFINES contains duplicate APP_FLAVOR'
        app_flavor_seen=true
        app_flavor="$value"
        ;;
      CLIENT_MODE)
        [ "$client_mode_seen" = false ] || \
          fail 'DART_DEFINES contains duplicate CLIENT_MODE'
        client_mode_seen=true
        client_mode="$value"
        ;;
      API_BASE_URL)
        [ "$api_base_url_seen" = false ] || \
          fail 'DART_DEFINES contains duplicate API_BASE_URL'
        api_base_url_seen=true
        api_base_url="$value"
        ;;
      LINE_CHANNEL_ID)
        [ "$line_channel_id_seen" = false ] || \
          fail 'DART_DEFINES contains duplicate LINE_CHANNEL_ID'
        line_channel_id_seen=true
        line_channel_id="$value"
        ;;
      GOOGLE_CLIENT_ID)
        [ "$google_client_id_seen" = false ] || \
          fail 'DART_DEFINES contains duplicate GOOGLE_CLIENT_ID'
        google_client_id_seen=true
        google_client_id="$value"
        ;;
      GOOGLE_SERVER_CLIENT_ID)
        [ "$google_server_client_id_seen" = false ] || \
          fail 'DART_DEFINES contains duplicate GOOGLE_SERVER_CLIENT_ID'
        google_server_client_id_seen=true
        google_server_client_id="$value"
        ;;
      APPLE_SIGN_IN_RUNTIME_IMPLEMENTED)
        [ "$apple_runtime_implemented_seen" = false ] || \
          fail 'DART_DEFINES contains duplicate APPLE_SIGN_IN_RUNTIME_IMPLEMENTED'
        apple_runtime_implemented_seen=true
        apple_runtime_implemented="$value"
        ;;
      *)
        # Flutter/system and non-release application definitions may coexist;
        # they are syntactically validated but do not influence this contract.
        ;;
    esac
  done

  [ "$app_flavor_seen" = true ] || \
    fail 'DART_DEFINES is missing APP_FLAVOR'
  [ "$client_mode_seen" = true ] || \
    fail 'DART_DEFINES is missing CLIENT_MODE'
}

require_real_client_defines() {
  [ "$api_base_url_seen" = true ] && [ -n "$api_base_url" ] && \
    [ "$line_channel_id_seen" = true ] && [ -n "$line_channel_id" ] && \
    [ "$google_client_id_seen" = true ] && [ -n "$google_client_id" ] && \
    [ "$google_server_client_id_seen" = true ] && \
    [ -n "$google_server_client_id" ] || \
    fail 'real iOS builds require each service DART_DEFINE exactly once'
}

portable_apple_entitlement_value() {
  awk '
    function trimmed(value) {
      sub(/^[[:space:]]+/, "", value)
      sub(/[[:space:]]+$/, "", value)
      return value
    }
    {
      line = trimmed($0)
      if (line == "<key>com.apple.developer.applesignin</key>") {
        if (found) {
          invalid = 1
          exit 1
        }
        found = 1
        state = 1
        next
      }
      if (state == 1) {
        if (line == "" || line ~ /^<!--.*-->$/) next
        if (line != "<array>") {
          invalid = 1
          exit 1
        }
        state = 2
        next
      }
      if (state == 2) {
        if (line == "" || line ~ /^<!--.*-->$/) next
        if (line == "<string>Default</string>") {
          defaults++
          next
        }
        if (line == "</array>") {
          if (defaults != 1) {
            invalid = 1
            exit 1
          }
          complete = 1
          state = 3
          next
        }
        invalid = 1
        exit 1
      }
    }
    END {
      if (invalid || found != 1 || complete != 1 || state != 3) exit 1
      print "Default"
    }
  ' "$1"
}

apple_entitlement_value() {
  entitlements_file="$1"
  kernel_name="$(/usr/bin/uname -s 2>/dev/null || printf 'unknown')"
  if [ "$kernel_name" = Darwin ]; then
    [ -x /usr/libexec/PlistBuddy ] || \
      fail 'macOS plist validator is unavailable'
    entitlement_container="$(/usr/libexec/PlistBuddy \
      -c 'Print :com.apple.developer.applesignin' \
      "$entitlements_file" 2>/dev/null)" || return 1
    [ "$(printf '%s\n' "$entitlement_container" | sed -n '1p')" = 'Array {' ] || \
      return 1
    first_entitlement="$(/usr/libexec/PlistBuddy \
      -c 'Print :com.apple.developer.applesignin:0' \
      "$entitlements_file" 2>/dev/null)" || return 1
    [ "$first_entitlement" = Default ] || return 1
    if /usr/libexec/PlistBuddy \
        -c 'Print :com.apple.developer.applesignin:1' \
        "$entitlements_file" >/dev/null 2>&1; then
      return 1
    fi
    printf 'Default\n'
    return
  fi
  portable_apple_entitlement_value "$entitlements_file"
}

require_external_value() {
  label="$1"
  value="$2"
  case "$value" in
    ''|'-'|*'$('*|*')'*) fail "$label must be supplied by the external signing environment" ;;
  esac
}

scan_dart_defines
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
  if [ "$api_base_url_seen" = true ] || [ "$line_channel_id_seen" = true ] || \
      [ "$google_client_id_seen" = true ] || \
      [ "$google_server_client_id_seen" = true ] || \
      [ "$apple_runtime_implemented_seen" = true ]; then
    fail 'development fake iOS builds must not contain service DART_DEFINES'
  fi
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

if { [ "$app_flavor" = staging ] || [ "$app_flavor" = production ]; } && \
    [ "$client_mode" = real ]; then
  require_real_client_defines
fi

if [ "$app_flavor" = staging ] && \
    [ "$apple_runtime_implemented_seen" = true ]; then
  fail 'staging iOS builds must not claim Apple runtime implementation'
fi
if [ "$app_flavor" = production ]; then
  if [ "$repository_status" = ready ]; then
    [ "$apple_runtime_implemented_seen" = true ] || \
      fail 'public iOS release is missing the Apple runtime implementation marker'
  elif [ "$apple_runtime_implemented_seen" = true ]; then
    fail 'Apple runtime implementation marker conflicts with repository status'
  fi
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
apple_entitlement="$(apple_entitlement_value "$entitlements")" || \
  fail 'public iOS release has an invalid Sign in with Apple entitlement structure'
[ "$apple_entitlement" = Default ] || \
  fail 'public iOS release has an invalid Sign in with Apple entitlement value'
