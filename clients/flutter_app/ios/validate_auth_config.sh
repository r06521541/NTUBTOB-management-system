#!/bin/sh
set -eu

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
      "$requested="*) printf '%s' "${decoded#*=}" ; IFS="$old_ifs"; return 0 ;;
    esac
  done
  IFS="$old_ifs"
}

app_flavor="$(dart_define APP_FLAVOR)"
client_mode="$(dart_define CLIENT_MODE)"
google_client_id="$(dart_define GOOGLE_CLIENT_ID)"
google_server_client_id="$(dart_define GOOGLE_SERVER_CLIENT_ID)"

if [ "$app_flavor" = development ] && [ "$client_mode" = fake ]; then
  if [ -n "$google_client_id" ] || [ -n "$google_server_client_id" ] || \
      [ -n "${GOOGLE_REVERSED_CLIENT_ID:-}" ]; then
    echo "error: development fake iOS build must not contain Google provider configuration" >&2
    exit 2
  fi
  exit 0
fi

if { [ "$app_flavor" != staging ] && [ "$app_flavor" != production ]; } || \
    [ "$client_mode" != real ]; then
  echo "error: iOS build mode is missing or invalid" >&2
  exit 2
fi

google_client_pattern='^[0-9A-Za-z][0-9A-Za-z._-]{5,199}\.apps\.googleusercontent\.com$'
printf '%s\n' "$google_client_id" | grep -Eq "$google_client_pattern" || {
  echo "error: GOOGLE_CLIENT_ID is missing or malformed" >&2
  exit 2
}
printf '%s\n' "$google_server_client_id" | grep -Eq "$google_client_pattern" || {
  echo "error: GOOGLE_SERVER_CLIENT_ID is missing or malformed" >&2
  exit 2
}
if [ "$google_client_id" = "$google_server_client_id" ]; then
  echo "error: iOS and Web server Google client IDs must be distinct" >&2
  exit 2
fi

expected_reversed_client_id="$(printf '%s\n' "$google_client_id" | awk -F. '{ for (i = NF; i > 1; i--) printf "%s.", $i; print $1 }')"
if [ "${GOOGLE_REVERSED_CLIENT_ID:-}" != "$expected_reversed_client_id" ]; then
  echo "error: GOOGLE_REVERSED_CLIENT_ID does not match GOOGLE_CLIENT_ID" >&2
  exit 2
fi

case "$GOOGLE_REVERSED_CLIENT_ID" in
  *'$('*|*')'*|*' '*|*'/'*)
    echo "error: GOOGLE_REVERSED_CLIENT_ID is malformed" >&2
    exit 2
    ;;
esac

grep -Fq '<string>$(GOOGLE_REVERSED_CLIENT_ID)</string>' \
  "${SRCROOT}/Runner/Info.plist" || {
    echo "error: Google callback URL scheme binding is missing" >&2
    exit 2
  }
