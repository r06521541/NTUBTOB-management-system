"""Default-unused fresh provider proof for requesting restricted erasure intent.

This does not authenticate an application session, verify a deletion job, or erase
anything. Provider verification must run outside DB transactions. The final local
call only decrypts a proof: it neither looks up nor creates an identity or Person.
Proofs can replay during their lifetime. A durable attempt-to-job binding is still
required before runtime wiring, including after cancellation of an earlier intent.
No raw provider assertion is retained in either encrypted envelope or the DTO.
"""

import base64
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .mobile_api import VerifiedAssertion, utc_now

RESTRICTED_ERASURE_PROOF_PURPOSE = "account_erasure_restricted_intent"
_PROVIDERS = frozenset({"apple", "google", "line"})
_TOKEN = re.compile(r"[A-Za-z0-9_-]+\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{6})?\+00:00\Z")
_COMMON_FIELDS = frozenset(
    {"attempt_id", "provider", "issued_at", "expires_at", "purpose", "audience"}
)
_KEY_DOMAIN = b"account-erasure-restricted-intent-aead-v1"
_AAD_PREFIX = "account-erasure-restricted-intent:"


class RestrictedErasureProofRejected(ValueError):
    """Fixed rejection without credentials, subjects, or underlying diagnostics."""


@dataclass(frozen=True, repr=False)
class FreshRestrictedErasureProof:
    attempt_id: str
    provider: str
    provider_subject: str
    authenticated_at: datetime
    expires_at: datetime
    purpose: str
    audience: str


def _reject(*_):
    raise RestrictedErasureProofRejected("invalid_restricted_erasure_proof") from None


def _text(value, limit):
    return type(value) is str and 1 <= len(value) <= limit and bool(value.strip())


def _utc(value):
    try:
        if (
            type(value) is not datetime
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            _reject()
        return value.astimezone(timezone.utc)
    except Exception:
        _reject()


def _date(value):
    if (
        type(value) is not str
        or not 25 <= len(value) <= 32
        or not _DATE.fullmatch(value)
    ):
        _reject()
    try:
        result = datetime.fromisoformat(value)
        if result.isoformat() != value:
            _reject()
        return _utc(result)
    except (ValueError, TypeError, OverflowError):
        _reject()


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            _reject()
        result[key] = value
    return result


def _decode(token, minimum, maximum):
    if (
        type(token) is not str
        or not minimum <= len(token) <= maximum
        or not _TOKEN.fullmatch(token)
    ):
        _reject()
    try:
        raw = base64.b64decode(
            token + "=" * (-len(token) % 4), altchars=b"-_", validate=True
        )
        if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != token:
            _reject()
        return raw
    except (ValueError, TypeError, UnicodeError):
        _reject()


class ErasureRestrictedProofService:
    # Fixed internal typed variants reuse validation/framing, never purpose/key/AAD.
    # These are not constructor options or authority supplied by a client.
    _purpose = RESTRICTED_ERASURE_PROOF_PURPOSE
    _key_domain = _KEY_DOMAIN
    _aad_prefix = _AAD_PREFIX

    def __init__(
        self,
        key: bytes,
        *,
        audience: str,
        lifetime: timedelta,
        providers: dict,
        clock: Callable[[], datetime] = utc_now,
    ):
        if (
            type(key) is not bytes
            or len(key) < 32
            or not _text(audience, 200)
            or type(lifetime) is not timedelta
            or not timedelta(0) < lifetime <= timedelta(minutes=5)
            or type(providers) is not dict
            or not callable(clock)
        ):
            _reject()
        for provider, config in providers.items():
            if (
                type(provider) is not str
                or provider not in _PROVIDERS
                or type(config) is not tuple
                or len(config) != 2
                or not callable(getattr(config[0], "verify", None))
                or not _text(config[1], 255)
            ):
                _reject()
        self._key = hmac.new(key, self._key_domain, hashlib.sha256).digest()
        self.audience, self.lifetime = audience, lifetime
        self.providers, self.clock = dict(providers), clock

    def _now(self):
        try:
            return _utc(self.clock())
        except Exception:
            _reject()

    def begin(self, provider: str) -> dict:
        """Generate a fresh attempt/nonce; accepts no identity, Person, or job ID."""
        if type(provider) is not str or provider not in self.providers:
            _reject()
        now = self._now()
        try:
            payload = dict(
                attempt_id=str(uuid4()),
                provider=provider,
                issued_at=now.isoformat(),
                expires_at=(now + self.lifetime).isoformat(),
                purpose=self._purpose,
                audience=self.audience,
                nonce=secrets.token_urlsafe(32),
            )
        except Exception:
            _reject()
        self._validate_challenge(payload, now)
        return dict(
            challenge_credential=self._seal("challenge", payload),
            nonce=payload["nonce"],
            provider=provider,
            expires_in=int(self.lifetime.total_seconds()),
        )

    def authenticate(self, challenge_credential: str, provider_assertion: str) -> str:
        """At most one injected provider call, outside DB transactions; no retry."""
        before = self._now()
        payload = self._open("challenge", challenge_credential)
        _, expiry = self._validate_challenge(payload, before)
        if not _text(provider_assertion, 16384):
            _reject()
        config = self.providers.get(payload["provider"])
        if config is None:
            _reject()
        verifier, provider_audience = config
        try:
            verified = verifier.verify(
                provider_assertion, provider_audience, payload["nonce"], before
            )
        except Exception:
            _reject()
        now = self._now()
        self._validate_challenge(payload, now)
        if (
            now < before
            or type(verified) is not VerifiedAssertion
            or type(verified.provider) is not str
            or verified.provider != payload["provider"]
            or type(verified.audience) is not str
            or verified.audience != provider_audience
            or type(verified.nonce) is not str
            or verified.nonce != payload["nonce"]
            or not _text(verified.subject, 255)
        ):
            _reject()
        provider_expiry = _utc(verified.expires_at)
        if provider_expiry <= now:
            _reject()
        payload.pop("nonce")
        payload.update(
            provider_subject=verified.subject,
            authenticated_at=now.isoformat(),
            expires_at=min(expiry, provider_expiry).isoformat(),
        )
        self._validate_proof(payload, now)
        return self._seal("verified", payload)

    def __call__(self, verified_credential: str) -> FreshRestrictedErasureProof:
        """Local decryption only; does not authorize deletion or prevent replay."""
        return self._validate_proof(
            self._open("verified", verified_credential), self._now()
        )

    def _seal(self, domain, payload):
        try:
            nonce = secrets.token_bytes(12)
            raw = nonce + AESGCM(self._key).encrypt(
                nonce,
                json.dumps(
                    payload, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode("utf-8"),
                (self._aad_prefix + domain).encode("ascii"),
            )
            token = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
            if not 80 <= len(token) <= 4096:
                _reject()
            return token
        except Exception:
            _reject()

    def _open(self, domain, token):
        try:
            raw = _decode(token, 80, 4096)
            payload = json.loads(
                AESGCM(self._key).decrypt(
                    raw[:12], raw[12:], (self._aad_prefix + domain).encode("ascii")
                ),
                object_pairs_hook=_pairs,
                parse_constant=_reject,
            )
            if type(payload) is not dict:
                _reject()
            return payload
        except (ValueError, TypeError, UnicodeError, InvalidTag, RecursionError):
            _reject()

    def _validate_common(self, payload, now, fields):
        if set(payload) != fields:
            _reject()
        try:
            attempt = payload["attempt_id"]
            if (
                type(attempt) is not str
                or len(attempt) != 36
                or str(UUID(attempt)) != attempt
                or UUID(attempt).version != 4
                or type(payload["purpose"]) is not str
                or payload["purpose"] != self._purpose
                or type(payload["audience"]) is not str
                or payload["audience"] != self.audience
                or type(payload["provider"]) is not str
                or payload["provider"] not in _PROVIDERS
            ):
                _reject()
            issued, expiry = _date(payload["issued_at"]), _date(payload["expires_at"])
            if (
                issued > now
                or expiry <= now
                or not timedelta(0) < expiry - issued <= self.lifetime
            ):
                _reject()
            return issued, expiry
        except (ValueError, TypeError, OverflowError):
            _reject()

    def _validate_challenge(self, payload, now):
        result = self._validate_common(payload, now, _COMMON_FIELDS | {"nonce"})
        if len(_decode(payload["nonce"], 43, 43)) != 32:
            _reject()
        return result

    def _validate_proof(self, payload, now):
        issued, expiry = self._validate_common(
            payload, now, _COMMON_FIELDS | {"provider_subject", "authenticated_at"}
        )
        authenticated = _date(payload["authenticated_at"])
        if (
            not _text(payload["provider_subject"], 255)
            or not issued <= authenticated <= now < expiry
        ):
            _reject()
        return self._proof_factory(
            payload, issued=issued, authenticated=authenticated, expiry=expiry
        )

    def _proof_factory(self, payload, *, issued, authenticated, expiry):
        # Preserve the original restricted-intent DTO (including no issued_at).
        return FreshRestrictedErasureProof(
            attempt_id=payload["attempt_id"],
            provider=payload["provider"],
            provider_subject=payload["provider_subject"],
            authenticated_at=authenticated,
            expires_at=expiry,
            purpose=payload["purpose"],
            audience=payload["audience"],
        )
