"""LINE Login Verify ID token endpoint adapter.

The raw token and nonce are sent only to LINE's documented endpoint.  They are
never included in exceptions or logs.  The transport is injectable so tests do
not perform external HTTP requests.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shared_module.mobile_api import (
    AuthenticationError,
    MobileApiError,
    VerifiedAssertion,
)

VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"


class LineVerificationUnavailable(MobileApiError):
    pass


class LineVerificationRateLimited(MobileApiError):
    code, status = "rate_limited", 429


def urlopen_transport(url: str, body: bytes, timeout: float) -> tuple[int, bytes]:
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
    def __init__(
        self,
        transport: Callable[[str, bytes, float], tuple[int, bytes]] = urlopen_transport,
        *,
        timeout: float = 5.0,
    ):
        if not 0 < timeout <= 10:
            raise ValueError("LINE verification timeout is out of bounds")
        self._transport, self._timeout = transport, timeout

    def verify(
        self, assertion: str, audience: str, nonce: str, now: datetime
    ) -> VerifiedAssertion:
        body = urlencode(
            {"id_token": assertion, "client_id": audience, "nonce": nonce}
        ).encode("ascii")
        try:
            status, raw = self._transport(VERIFY_URL, body, self._timeout)
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
