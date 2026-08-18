"""Offline LINE ID-token signature verifier adapter.

The public key is deployment configuration, not fetched by this service. Raw
assertions and nonce values are never logged or persisted by this adapter.
"""

from datetime import datetime, timezone

import jwt
from jwt import InvalidTokenError
from shared_module.mobile_api import AuthenticationError, VerifiedAssertion


class LineJwtVerifier:
    def __init__(self, public_key: str):
        if not public_key:
            raise RuntimeError("MOBILE_LINE_PUBLIC_KEY is required")
        self._public_key = public_key

    def verify(
        self, assertion: str, audience: str, nonce: str, now: datetime
    ) -> VerifiedAssertion:
        try:
            claims = jwt.decode(
                assertion,
                self._public_key,
                algorithms=["RS256"],
                audience=audience,
                issuer="https://access.line.me",
                options={"require": ["exp", "iss", "aud", "sub", "nonce"]},
            )
            if claims["nonce"] != nonce:
                raise AuthenticationError("invalid provider assertion")
            expires_at = datetime.fromtimestamp(claims["exp"], timezone.utc)
            if expires_at <= now:
                raise AuthenticationError("invalid provider assertion")
            return VerifiedAssertion(
                "line", claims["sub"], audience, claims["nonce"], expires_at
            )
        except (InvalidTokenError, KeyError, TypeError, ValueError):
            raise AuthenticationError("invalid provider assertion") from None
