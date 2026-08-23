"""Google ID token adapter with injected verification for offline tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Mapping

from shared_module.mobile_api import AuthenticationError, VerifiedAssertion


GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def verify_with_google_auth(assertion: str) -> Mapping[str, object]:
    """Verify signature and expiry through Google's supported Python library."""
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import verify_oauth2_token

    return verify_oauth2_token(assertion, Request(), audience=None)


class GoogleIdTokenVerifier:
    def __init__(
        self,
        verify_token: Callable[[str], Mapping[str, object]] = verify_with_google_auth,
        *,
        audiences: tuple[str, ...],
    ):
        if not audiences or any(not value for value in audiences):
            raise ValueError("Google audience allowlist is required")
        self._verify_token = verify_token
        self._audiences = frozenset(audiences)

    def verify(
        self,
        assertion: str,
        _audience: str,
        _nonce: str | None,
        now: datetime,
    ) -> VerifiedAssertion:
        try:
            claims = self._verify_token(assertion)
            audience, subject = claims["aud"], claims["sub"]
            expires_at = datetime.fromtimestamp(int(claims["exp"]), timezone.utc)
            if (
                claims.get("iss") not in GOOGLE_ISSUERS
                or not isinstance(audience, str)
                or audience not in self._audiences
                or not isinstance(subject, str)
                or not subject
                or expires_at <= now.astimezone(timezone.utc)
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            raise AuthenticationError("invalid provider assertion") from None
        except Exception:
            raise AuthenticationError("Google verification unavailable") from None
        return VerifiedAssertion("google", subject, audience, None, expires_at)
