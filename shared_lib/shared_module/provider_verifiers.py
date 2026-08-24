"""Canonical Google and LINE ID-token verification adapters."""

from __future__ import annotations
import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .mobile_api import AuthenticationError, MobileApiError, VerifiedAssertion

GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
LINE_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"


def verify_with_google_auth(assertion):
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2.id_token import verify_oauth2_token

    return verify_oauth2_token(assertion, GoogleRequest(), audience=None)


class GoogleIdTokenVerifier:
    def __init__(self, verify_token=verify_with_google_auth, *, audiences):
        if not audiences or any(not value for value in audiences):
            raise ValueError("Google audience allowlist is required")
        self._verify_token, self._audiences = verify_token, frozenset(audiences)

    def verify(self, assertion, _audience, nonce, now):
        try:
            claims = self._verify_token(assertion)
            audience, subject = claims["aud"], claims["sub"]
            expires_at = datetime.fromtimestamp(int(claims["exp"]), timezone.utc)
            if (
                claims.get("iss") not in GOOGLE_ISSUERS
                or audience not in self._audiences
                or not isinstance(audience, str)
                or not isinstance(subject, str)
                or not subject
                or expires_at <= now.astimezone(timezone.utc)
                or (nonce is not None and claims.get("nonce") != nonce)
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            raise AuthenticationError("invalid provider assertion") from None
        except Exception:
            raise AuthenticationError("Google verification unavailable") from None
        return VerifiedAssertion("google", subject, audience, nonce, expires_at)


class LineVerificationUnavailable(MobileApiError):
    pass


class LineVerificationRateLimited(MobileApiError):
    code, status = "rate_limited", 429


def line_urlopen_transport(url, body, timeout):
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read(16_385)
    except HTTPError as error:
        return error.code, error.read(16_385)
    except (TimeoutError, URLError, OSError):
        raise LineVerificationUnavailable("LINE verification unavailable") from None


class LineIdTokenVerifier:
    def __init__(self, transport=line_urlopen_transport, *, timeout=5.0):
        if not 0 < timeout <= 10:
            raise ValueError("LINE verification timeout is out of bounds")
        self._transport, self._timeout = transport, timeout

    def verify(self, assertion, audience, nonce, now):
        body = urlencode(
            {"id_token": assertion, "client_id": audience, "nonce": nonce}
        ).encode("ascii")
        try:
            status, raw = self._transport(LINE_VERIFY_URL, body, self._timeout)
        except LineVerificationUnavailable:
            raise
        except Exception:
            raise LineVerificationUnavailable("LINE verification unavailable") from None
        if status in {400, 401, 403}:
            raise AuthenticationError("invalid provider assertion")
        if status == 429:
            raise LineVerificationRateLimited("LINE verification rate limited")
        if status >= 500:
            raise LineVerificationUnavailable("LINE verification unavailable")
        if status != 200 or len(raw) > 16_384:
            raise AuthenticationError("invalid provider assertion")
        try:
            claims = json.loads(raw)
            expires_at = datetime.fromtimestamp(claims["exp"], timezone.utc)
            if (
                not isinstance(claims, dict)
                or claims.get("iss") != "https://access.line.me"
                or claims.get("aud") != audience
                or claims.get("nonce") != nonce
                or not isinstance(claims.get("sub"), str)
                or not claims["sub"]
                or expires_at <= now.astimezone(timezone.utc)
            ):
                raise ValueError
        except (TypeError, ValueError, KeyError, json.JSONDecodeError, OverflowError):
            raise AuthenticationError("invalid provider assertion") from None
        return VerifiedAssertion("line", claims["sub"], audience, nonce, expires_at)
