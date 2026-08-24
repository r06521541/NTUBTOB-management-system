#!/bin/sh
set -eu

case "${GOOGLE_REVERSED_CLIENT_ID:-}" in
  com.googleusercontent.apps.[0-9A-Za-z._-]*) ;;
  *)
    echo "error: Owner-approved GOOGLE_REVERSED_CLIENT_ID is required" >&2
    exit 2
    ;;
esac

case "$GOOGLE_REVERSED_CLIENT_ID" in
  *'$('*|*')'*|*' '*|*'/'*)
    echo "error: GOOGLE_REVERSED_CLIENT_ID is malformed" >&2
    exit 2
    ;;
esac

binding_found=false
while IFS= read -r line; do
  case "$line" in
    *'<string>$(GOOGLE_REVERSED_CLIENT_ID)</string>'*) binding_found=true ;;
  esac
done < "${SRCROOT}/Runner/Info.plist"

$binding_found || {
    echo "error: Google callback URL scheme binding is missing" >&2
    exit 2
  }
