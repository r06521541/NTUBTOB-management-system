"""Canonical Google, LINE, and Apple ID-token verification adapters."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .mobile_api import AuthenticationError, MobileApiError, VerifiedAssertion

GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
LINE_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"
APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_JWKS_MAX_BYTES = 65_536
APPLE_JWT_MAX_BYTES = 16_384
APPLE_JWKS_FAILURE_BACKOFF = timedelta(minutes=1)
_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")
_APPLE_KID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


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


class AppleVerificationUnavailable(MobileApiError):
    """Apple public-key retrieval was unavailable without exposing provider data."""


def apple_jwks_urlopen_transport(url, timeout):
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read(APPLE_JWKS_MAX_BYTES + 1)
    except HTTPError as error:
        return error.code, error.read(APPLE_JWKS_MAX_BYTES + 1)
    except (TimeoutError, URLError, OSError):
        raise AppleVerificationUnavailable("Apple verification unavailable") from None


def _strict_json(raw: bytes) -> object:
    def no_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    try:
        return json.loads(raw, object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise AuthenticationError("invalid provider assertion") from None


def _decode_base64url(value: object, *, maximum: int) -> bytes:
    try:
        if (
            not isinstance(value, str)
            or not value
            or len(value) > maximum
            or _BASE64URL.fullmatch(value) is None
        ):
            raise ValueError
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
        if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value:
            raise ValueError
        return decoded
    except (binascii.Error, UnicodeError, ValueError):
        raise AuthenticationError("invalid provider assertion") from None


def _apple_public_key(value: object):
    if not isinstance(value, dict) or set(value) != {
        "kty",
        "kid",
        "use",
        "alg",
        "n",
        "e",
    }:
        raise AuthenticationError("invalid provider assertion")
    if (
        value["kty"] != "RSA"
        or value["use"] != "sig"
        or value["alg"] != "RS256"
        or not isinstance(value["kid"], str)
        or _APPLE_KID.fullmatch(value["kid"]) is None
    ):
        raise AuthenticationError("invalid provider assertion")
    modulus = _decode_base64url(value["n"], maximum=1024)
    exponent = _decode_base64url(value["e"], maximum=8)
    try:
        if modulus.startswith(b"\x00") or exponent.startswith(b"\x00"):
            raise ValueError
        modulus_number = int.from_bytes(modulus, "big")
        exponent_number = int.from_bytes(exponent, "big")
        if not 2048 <= modulus_number.bit_length() <= 4096 or exponent_number != 65537:
            raise ValueError
        return rsa.RSAPublicNumbers(exponent_number, modulus_number).public_key()
    except ValueError:
        raise AuthenticationError("invalid provider assertion") from None


class AppleJwkCache:
    """A bounded in-process cache for Apple's rotating public signing keys."""

    def __init__(
        self,
        transport=apple_jwks_urlopen_transport,
        *,
        timeout=5.0,
        ttl=timedelta(minutes=15),
    ):
        if not 0 < timeout <= 10 or not timedelta(minutes=1) <= ttl <= timedelta(
            hours=1
        ):
            raise ValueError("Apple JWK cache bounds are invalid")
        self._transport = transport
        self._timeout = timeout
        self._ttl = ttl
        self._keys = {}
        self._expires_at = None
        self._forced_refresh_used = False
        self._refresh_retry_at = None
        self._lock = threading.Lock()

    def key(self, kid: str, now: datetime):
        if (
            not isinstance(kid, str)
            or _APPLE_KID.fullmatch(kid) is None
            or now.tzinfo is None
        ):
            raise AuthenticationError("invalid provider assertion")
        normalized_now = now.astimezone(timezone.utc)
        with self._lock:
            if self._expires_at is None or self._expires_at <= normalized_now:
                self._refresh(normalized_now)
                self._forced_refresh_used = False
            key = self._keys.get(kid)
            if key is not None:
                return key
            # Permit one early refresh per fresh cache window for normal rotation.
            # A failed attempt remains governed by the refresh backoff and may
            # recover once its deadline arrives; only a successful refresh uses
            # the window's early-refresh allowance.
            if self._forced_refresh_used:
                raise AuthenticationError("invalid provider assertion")
            self._refresh(normalized_now)
            self._forced_refresh_used = True
            key = self._keys.get(kid)
            if key is None:
                raise AuthenticationError("invalid provider assertion")
            return key

    def _refresh(self, now: datetime) -> None:
        if self._refresh_retry_at is not None and now < self._refresh_retry_at:
            raise AppleVerificationUnavailable("Apple verification unavailable")
        # Set the deadline before transport and retain the greatest observed
        # deadline. A clock rollback therefore cannot reopen the retry window.
        retry_at = now + APPLE_JWKS_FAILURE_BACKOFF
        if self._refresh_retry_at is None or self._refresh_retry_at < retry_at:
            self._refresh_retry_at = retry_at
        try:
            status, raw = self._transport(APPLE_JWKS_URL, self._timeout)
        except AppleVerificationUnavailable:
            raise
        except Exception:
            raise AppleVerificationUnavailable(
                "Apple verification unavailable"
            ) from None
        if status != 200:
            raise AppleVerificationUnavailable(
                "Apple verification unavailable"
            ) from None
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= APPLE_JWKS_MAX_BYTES:
            raise AuthenticationError("invalid provider assertion")
        payload = _strict_json(raw)
        if (
            not isinstance(payload, dict)
            or set(payload) != {"keys"}
            or not isinstance(payload["keys"], list)
            or not 1 <= len(payload["keys"]) <= 10
        ):
            raise AuthenticationError("invalid provider assertion")
        keys = {}
        for item in payload["keys"]:
            public_key = _apple_public_key(item)
            if item["kid"] in keys:
                raise AuthenticationError("invalid provider assertion")
            keys[item["kid"]] = public_key
        self._keys = keys
        self._expires_at = now + self._ttl
        self._refresh_retry_at = None


class AppleIdTokenVerifier:
    """Verify a nonce-bound Apple ID token and expose only its stable subject."""

    def __init__(self, key_cache=None):
        self._key_cache = key_cache or AppleJwkCache()

    def verify(self, assertion, audience, nonce, now):
        try:
            if (
                not isinstance(assertion, str)
                or not 1 <= len(assertion) <= APPLE_JWT_MAX_BYTES
                or not isinstance(audience, str)
                or not audience
                or not isinstance(nonce, str)
                or not nonce
                or now.tzinfo is None
            ):
                raise AuthenticationError("invalid provider assertion")
            parts = assertion.split(".")
            if len(parts) != 3:
                raise AuthenticationError("invalid provider assertion")
            header = _strict_json(_decode_base64url(parts[0], maximum=2048))
            claims = _strict_json(_decode_base64url(parts[1], maximum=12_288))
            signature = _decode_base64url(parts[2], maximum=1024)
            if (
                not isinstance(header, dict)
                or not {"alg", "kid"} <= set(header) <= {"alg", "kid", "typ"}
                or header["alg"] != "RS256"
                or ("typ" in header and header["typ"] != "JWT")
            ):
                raise AuthenticationError("invalid provider assertion")
            public_key = self._key_cache.key(header["kid"], now)
            public_key.verify(
                signature,
                (parts[0] + "." + parts[1]).encode("ascii"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            normalized_now = int(now.astimezone(timezone.utc).timestamp())
            expected_nonce = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
            if not isinstance(claims, dict):
                raise AuthenticationError("invalid provider assertion")
            expires_at = claims.get("exp")
            issued_at = claims.get("iat")
            subject = claims.get("sub")
            if (
                claims.get("iss") != APPLE_ISSUER
                or claims.get("aud") != audience
                or claims.get("nonce") != expected_nonce
                or type(expires_at) is not int
                or type(issued_at) is not int
                or expires_at <= normalized_now
                or issued_at > normalized_now + 60
                or issued_at >= expires_at
                or expires_at - issued_at > 86_400
                or not isinstance(subject, str)
                or not 1 <= len(subject) <= 255
                or not subject.isascii()
                or not subject.isprintable()
            ):
                raise AuthenticationError("invalid provider assertion")
            return VerifiedAssertion(
                "apple",
                subject,
                audience,
                nonce,
                datetime.fromtimestamp(expires_at, timezone.utc),
            )
        except AppleVerificationUnavailable:
            raise
        except AuthenticationError:
            raise
        except (InvalidSignature, OverflowError, TypeError, ValueError):
            raise AuthenticationError("invalid provider assertion") from None
