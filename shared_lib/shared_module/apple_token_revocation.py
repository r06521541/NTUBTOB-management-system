"""Default-unused Apple refresh-token revocation, never a retry/authority layer.

Only invoke as the trusted prepared effect AFTER the erasure executor's durable
dispatch fence. Callers bind the exact credential version before preparation.
No credential lookup, persistence, logging, automatic retry or account deletion.
Apple documents empty HTTP 200 for invalidated or previously invalidated tokens:
https://developer.apple.com/documentation/signinwithapplerestapi/revoke-tokens
"""

from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

_URL = "https://appleid.apple.com/auth/revoke"


class AppleRevocationUnknown(RuntimeError):
    """Dispatch may have occurred; reconcile, never automatically retry."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _transport(url, body, timeout):
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            # The documented successful response is empty; never retain a body.
            return response.status, response.read(1)
    except HTTPError as error:
        try:
            return error.code, b""
        finally:
            error.close()


class AppleTokenRevoker:
    def __init__(self, *, transport=_transport):
        if not callable(transport):
            raise ValueError("invalid_revocation_configuration")
        self._transport = transport

    def revoke(self, *, client_id, client_secret, token):
        for value in (client_id, client_secret, token):
            if (
                type(value) is not str
                or not 1 <= len(value) <= 65536
                or not value.isascii()
                or any(ord(char) < 33 or ord(char) == 127 for char in value)
            ):
                raise ValueError("invalid_revocation_input")
        body = urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "token": token,
                "token_type_hint": "refresh_token",
            }
        ).encode("ascii")
        try:
            status, payload = self._transport(_URL, body, 5.0)
            if type(status) is int and type(payload) is bytes:
                if status == 200 and payload == b"":
                    return "succeeded"
                if status in (400, 401, 403):
                    return "manual_action_needed"
        except Exception:
            raise AppleRevocationUnknown("apple_revocation_unknown") from None
        raise AppleRevocationUnknown("apple_revocation_unknown") from None
