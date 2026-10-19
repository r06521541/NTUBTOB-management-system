"""Default-unused server challenge exchange, separate from login authorization.

begin() accepts only a context from the receipt-authorized database lookup. Provider
verification in authenticate() runs OUTSIDE database transactions. The callable
interface only decrypts a local proof for the transaction coordinator. A successful
exchange proves provider participation with a fresh server nonce, not that a password
was retyped. No provider code redemption, account creation or runtime wiring occurs.
"""

import base64
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .mobile_api import MAX_POSTGRESQL_BIGINT, VerifiedAssertion, utc_now
from .portal_data.erasure_context import ErasureVerificationContext
from .portal_data.erasure_verification import (
    ERASURE_VERIFICATION_PURPOSE,
    ErasureVerificationRejected,
    FreshErasureProof,
)

_TOKEN = re.compile(r"[A-Za-z0-9_-]+\Z")
_FIELDS = frozenset(
    {
        "job_id",
        "identity_id",
        "provider",
        "provider_subject",
        "identity_generation",
        "target_kind",
        "person_id",
        "target_generation",
        "authenticated_at",
        "expires_at",
        "purpose",
        "audience",
    }
)


def _reject():
    raise ErasureVerificationRejected("invalid_erasure_proof") from None


def _utc(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        _reject()
    return value.astimezone(timezone.utc)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            _reject()
        result[key] = value
    return result


class ErasureProofService:
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
            raise ValueError("invalid erasure proof configuration")
        for provider, config in providers.items():
            if (
                provider not in {"line", "apple", "google"}
                or type(config) is not tuple
                or len(config) != 2
                or not callable(getattr(config[0], "verify", None))
                or type(config[1]) is not str
                or not 1 <= len(config[1]) <= 255
            ):
                raise ValueError("invalid erasure provider configuration")
        self._key = hmac.new(
            key, b"account-erasure-proof-aead-v1", hashlib.sha256
        ).digest()
        self.audience, self.lifetime = audience, lifetime
        self.providers, self.clock = dict(providers), clock

    def begin(self, context: ErasureVerificationContext) -> dict:
        """Internal only: context is authorized by receipt lookup, not client JSON."""
        if type(context) is not ErasureVerificationContext:
            _reject()
        now = _utc(self.clock())
        if (
            _utc(context.requested_at) > now
            or type(context.provider) is not str
            or context.provider not in self.providers
        ):
            _reject()
        payload = asdict(context)
        payload.pop("requested_at")
        payload.update(
            purpose=ERASURE_VERIFICATION_PURPOSE,
            audience=self.audience,
            authenticated_at=now.isoformat(),
            expires_at=(now + self.lifetime).isoformat(),
        )
        self._validate(payload, now)
        # The nonce is generated here and encrypted with the full target binding.
        payload["nonce"] = secrets.token_urlsafe(32)
        return dict(
            challenge_credential=self._seal("challenge", payload),
            nonce=payload["nonce"],
            provider=context.provider,
            expires_in=int(self.lifetime.total_seconds()),
        )

    def authenticate(self, challenge_credential: str, provider_assertion: str) -> str:
        """One verification call, no retry or DB access; caller must hold no DB TX."""
        now = _utc(self.clock())
        payload = self._open("challenge", challenge_credential)
        if set(payload) != _FIELDS | {"nonce"}:
            _reject()
        nonce = payload.pop("nonce")
        if type(nonce) is not str or len(nonce) != 43 or not _TOKEN.fullmatch(nonce):
            _reject()
        proof = self._validate(payload, now)
        if (
            type(provider_assertion) is not str
            or not 1 <= len(provider_assertion) <= 16384
        ):
            _reject()
        config = self.providers.get(proof.provider)
        if config is None:
            _reject()
        verifier, provider_audience = config
        try:
            verified = verifier.verify(
                provider_assertion, provider_audience, nonce, now
            )
        except Exception:
            _reject()
        now = _utc(self.clock())
        self._validate(payload, now)  # Do not extend a challenge during slow I/O.
        if (
            type(verified) is not VerifiedAssertion
            or verified.provider != proof.provider
            or verified.subject != proof.provider_subject
            or verified.audience != provider_audience
            or verified.nonce != nonce
            or _utc(verified.expires_at) <= now
        ):
            _reject()
        payload["authenticated_at"] = now.isoformat()
        payload["expires_at"] = min(
            proof.expires_at, _utc(verified.expires_at)
        ).isoformat()
        return self._seal("verified", payload)

    def __call__(self, assertion: str) -> FreshErasureProof:
        """Local-only verifier for ErasureVerificationCoordinator; never provider I/O."""
        return self._validate(self._open("verified", assertion), _utc(self.clock()))

    def _seal(self, domain: str, payload: dict) -> str:
        nonce = secrets.token_bytes(12)
        sealed = nonce + AESGCM(self._key).encrypt(
            nonce,
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            ("account-erasure:" + domain).encode("ascii"),
        )
        token = base64.urlsafe_b64encode(sealed).rstrip(b"=").decode("ascii")
        if not 80 <= len(token) <= 4096:
            _reject()
        return token

    def _open(self, domain: str, token: str) -> dict:
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
                    raw[:12], raw[12:], ("account-erasure:" + domain).encode("ascii")
                ),
                object_pairs_hook=_pairs,
            )
            if type(payload) is not dict:
                _reject()
            return payload
        except (ValueError, TypeError, UnicodeError, InvalidTag):
            _reject()

    def _validate(self, payload: dict, now: datetime) -> FreshErasureProof:
        if set(payload) != _FIELDS:
            _reject()
        try:
            for name in ("job_id", "identity_generation", "target_generation"):
                value = payload[name]
                if type(value) is not str or str(UUID(value)) != value:
                    _reject()
            if (
                payload["purpose"] != ERASURE_VERIFICATION_PURPOSE
                or payload["audience"] != self.audience
                or type(payload["identity_id"]) is not int
                or not 0 < payload["identity_id"] <= MAX_POSTGRESQL_BIGINT
                or type(payload["provider"]) is not str
                or payload["provider"] not in {"line", "apple", "google"}
                or type(payload["provider_subject"]) is not str
                or not 1 <= len(payload["provider_subject"]) <= 255
                or type(payload["target_kind"]) is not str
                or payload["target_kind"] not in {"person", "pending_identity"}
                or (
                    payload["target_kind"] == "person"
                    and (
                        type(payload["person_id"]) is not int
                        or not 0 < payload["person_id"] <= MAX_POSTGRESQL_BIGINT
                    )
                )
                or (
                    payload["target_kind"] == "pending_identity"
                    and payload["person_id"] is not None
                )
            ):
                _reject()
            start = _utc(datetime.fromisoformat(payload["authenticated_at"]))
            expiry = _utc(datetime.fromisoformat(payload["expires_at"]))
            if (
                start > now
                or expiry <= now
                or expiry <= start
                or expiry - start > self.lifetime
            ):
                _reject()
            return FreshErasureProof(
                **{**payload, "authenticated_at": start, "expires_at": expiry}
            )
        except (ValueError, TypeError, OverflowError):
            _reject()
