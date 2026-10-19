"""Default-unused cancellation proof; not account authorization or cancellation.

Only receipt-authorized server code may supply CancellationContext. The challenge
binds a job/target generation, NOT a preselected identity. A provider's subject is
learned after its fresh nonce assertion is verified outside database transactions.
The coordinator must resolve that current identity, recheck the exact job/target,
freshness and dispatch fence under locks, and commit before reporting cancellation.
Proofs are stateless and may replay within their lifetime; locked job state, not
this codec, must enforce the terminal cancellation transition.
No session, provider credential, database row or runtime composition is changed.
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
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .mobile_api import VerifiedAssertion, utc_now

CANCELLATION_PROOF_PURPOSE = "account_erasure_cancellation"
_PROVIDERS = frozenset({"apple", "google", "line"})
_TOKEN = re.compile(r"[A-Za-z0-9_-]+\Z")
_COMMON_FIELDS = frozenset(
    {
        "job_id",
        "target_kind",
        "target_generation",
        "provider",
        "issued_at",
        "expires_at",
        "purpose",
        "audience",
    }
)


class CancellationProofRejected(ValueError):
    """Fixed boundary rejection; supplied credentials/details are never returned."""


@dataclass(frozen=True, repr=False)
class CancellationContext:
    job_id: str
    target_kind: str
    target_generation: str
    requested_at: datetime


@dataclass(frozen=True, repr=False)
class FreshCancellationProof:
    job_id: str
    target_kind: str
    target_generation: str
    provider: str
    provider_subject: str
    issued_at: datetime
    authenticated_at: datetime
    expires_at: datetime
    purpose: str
    audience: str


def _reject(*_):
    raise CancellationProofRejected("invalid_cancellation_proof") from None


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


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            _reject()
        result[key] = value
    return result


class CancellationProofService:
    # Internal typed variants may reuse framing, never key/AAD/purpose or DTOs.
    _domain = "account-erasure-cancellation"
    _purpose = CANCELLATION_PROOF_PURPOSE
    _context_type = CancellationContext
    _proof_type = FreshCancellationProof

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
            or type(audience) is not str
            or not 1 <= len(audience) <= 200
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
                or type(config[1]) is not str
                or not 1 <= len(config[1]) <= 255
            ):
                _reject()
        self._key = hmac.new(
            key, (self._domain + "-aead-v1").encode("ascii"), hashlib.sha256
        ).digest()
        self.audience, self.lifetime = audience, lifetime
        self.providers, self.clock = dict(providers), clock

    def _now(self):
        try:
            return _utc(self.clock())
        except Exception:
            _reject()

    def begin(self, context: CancellationContext, provider: str) -> dict:
        """Internal receipt-bound context only; no identity selection or provider I/O."""
        if (
            type(context) is not self._context_type
            or type(provider) is not str
            or provider not in self.providers
        ):
            _reject()
        now = self._now()
        if _utc(context.requested_at) > now:
            _reject()
        try:
            expiry = now + self.lifetime
        except OverflowError:
            _reject()
        payload = dict(
            job_id=context.job_id,
            target_kind=context.target_kind,
            target_generation=context.target_generation,
            provider=provider,
            issued_at=now.isoformat(),
            expires_at=expiry.isoformat(),
            purpose=self._purpose,
            audience=self.audience,
            nonce=secrets.token_urlsafe(32),
        )
        self._validate_challenge(payload, now)
        return dict(
            challenge_credential=self._seal("challenge", payload),
            nonce=payload["nonce"],
            provider=provider,
            expires_in=int(self.lifetime.total_seconds()),
        )

    def authenticate(self, challenge_credential: str, provider_assertion: str) -> str:
        """One injected provider verification, outside DB transactions; no retries."""
        now = self._now()
        payload = self._open("challenge", challenge_credential)
        _, expiry = self._validate_challenge(payload, now)
        if (
            type(provider_assertion) is not str
            or not 1 <= len(provider_assertion) <= 16384
        ):
            _reject()
        config = self.providers.get(payload["provider"])
        if config is None:
            _reject()
        verifier, audience = config
        try:
            verified = verifier.verify(
                provider_assertion, audience, payload["nonce"], now
            )
        except Exception:
            _reject()
        now = self._now()
        self._validate_challenge(payload, now)
        if (
            type(verified) is not VerifiedAssertion
            or verified.provider != payload["provider"]
            or verified.audience != audience
            or verified.nonce != payload["nonce"]
            or type(verified.subject) is not str
            or not 1 <= len(verified.subject) <= 255
            or _utc(verified.expires_at) <= now
        ):
            _reject()
        payload.pop("nonce")
        payload.update(
            provider_subject=verified.subject,
            authenticated_at=now.isoformat(),
            expires_at=min(expiry, _utc(verified.expires_at)).isoformat(),
        )
        # issued_at is deliberately unchanged; authentication does not renew it.
        self._validate_proof(payload, now)
        return self._seal("verified", payload)

    def __call__(self, assertion: str) -> FreshCancellationProof:
        """Local-only validation; does not resolve identities or authorize a DB write."""
        return self._validate_proof(self._open("verified", assertion), self._now())

    def _seal(self, domain, payload):
        nonce = secrets.token_bytes(12)
        raw = nonce + AESGCM(self._key).encrypt(
            nonce,
            json.dumps(
                payload, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8"),
            (self._domain + ":" + domain).encode("ascii"),
        )
        token = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        if not 80 <= len(token) <= 4096:
            _reject()
        return token

    def _open(self, domain, token):
        try:
            if (
                type(token) is not str
                or not 80 <= len(token) <= 4096
                or not _TOKEN.fullmatch(token)
            ):
                _reject()
            raw = base64.b64decode(
                token + "=" * (-len(token) % 4), altchars=b"-_", validate=True
            )
            if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != token:
                _reject()
            payload = json.loads(
                AESGCM(self._key).decrypt(
                    raw[:12],
                    raw[12:],
                    (self._domain + ":" + domain).encode("ascii"),
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
            for field in ("job_id", "target_generation"):
                value = payload[field]
                if (
                    type(value) is not str
                    or len(value) != 36
                    or str(UUID(value)) != value
                ):
                    _reject()
            if (
                payload["purpose"] != self._purpose
                or payload["audience"] != self.audience
                or type(payload["provider"]) is not str
                or payload["provider"] not in _PROVIDERS
                or type(payload["target_kind"]) is not str
                or payload["target_kind"] not in {"person", "pending_identity"}
            ):
                _reject()
            issued = _utc(datetime.fromisoformat(payload["issued_at"]))
            expiry = _utc(datetime.fromisoformat(payload["expires_at"]))
            if (
                issued > now
                or now - issued > self.lifetime
                or expiry <= now
                or not timedelta(0) < expiry - issued <= self.lifetime
            ):
                _reject()
            return issued, expiry
        except (ValueError, TypeError, OverflowError):
            _reject()

    def _validate_challenge(self, payload, now):
        issued, expiry = self._validate_common(payload, now, _COMMON_FIELDS | {"nonce"})
        nonce = payload["nonce"]
        if type(nonce) is not str or len(nonce) != 43 or not _TOKEN.fullmatch(nonce):
            _reject()
        return issued, expiry

    def _validate_proof(self, payload, now):
        issued, expiry = self._validate_common(
            payload, now, _COMMON_FIELDS | {"provider_subject", "authenticated_at"}
        )
        try:
            authenticated = _utc(datetime.fromisoformat(payload["authenticated_at"]))
            if (
                type(payload["provider_subject"]) is not str
                or not 1 <= len(payload["provider_subject"]) <= 255
                or not issued <= authenticated <= now
                or now - authenticated > self.lifetime
                or expiry <= authenticated
            ):
                _reject()
            return self._proof_type(
                **{
                    **payload,
                    "issued_at": issued,
                    "authenticated_at": authenticated,
                    "expires_at": expiry,
                }
            )
        except (ValueError, TypeError, OverflowError):
            _reject()
