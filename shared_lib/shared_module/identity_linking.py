"""Purpose-separated, short-lived proofs for cross-provider identity linking."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .mobile_api import (
    MAX_POSTGRESQL_BIGINT,
    AuthenticationError,
    Conflict,
    InvalidArgument,
    secret_hash,
)


PROOF_TTL = timedelta(minutes=5)
PROVIDERS = {"line", "google"}


class IdentityLinkConflict(Conflict):
    pass


@dataclass(frozen=True)
class CandidateProof:
    identity_id: int
    provider: str
    version_hash: str
    assertion_hash: str
    attempt_hash: str
    binding_hash: str
    jti: str


@dataclass(frozen=True)
class FreshIdentityProof:
    identity_id: int
    person_id: int
    provider: str
    version_hash: str
    candidate_jti: str
    attempt_hash: str
    binding_hash: str
    jti: str


@dataclass(frozen=True)
class InternalWebPrincipal:
    person_id: int
    identity_id: int
    member_id: int | None


@dataclass(frozen=True)
class IdentityLinkResult:
    status: str
    mobile_session: dict | None = None
    web_principal: InternalWebPrincipal | None = None

    def mobile_public(self) -> dict:
        return {"status": self.status, "session": self.mobile_session}


class IdentityLinkProofCodec:
    def __init__(self, key: bytes):
        if len(key) < 32:
            raise ValueError("identity-link proof key must contain at least 32 bytes")
        self._key = key
        self._encryption_key = hmac.new(
            key, b"identity-link-proof-aead-v1", hashlib.sha256
        ).digest()

    @staticmethod
    def _utc_microseconds(value: datetime) -> str:
        if value.tzinfo is None:
            raise ValueError("identity timestamp must be timezone-aware")
        return (
            value.astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )

    def identity_version_hash(self, identity_id: int, updated_at: datetime) -> str:
        canonical = (
            f"identity-version-v1:{identity_id}:{self._utc_microseconds(updated_at)}"
        )
        return hmac.new(
            self._key, canonical.encode("ascii"), hashlib.sha256
        ).hexdigest()

    def audit_request_id(self, candidate_jti: str) -> str:
        digest = hmac.new(
            self._key,
            f"identity-link-audit-v1:{candidate_jti}".encode("ascii"),
            hashlib.sha256,
        ).hexdigest()[:40]
        return f"identity-self-link-{digest}"

    def issue_candidate(self, **values) -> str:
        now = values.pop("now")
        updated_at = values.pop("identity_updated_at")
        payload = {
            "purpose": "identity_link_candidate",
            "iid": values.pop("identity_id"),
            "provider": values.pop("provider"),
        }
        identity_id = payload["iid"]
        payload["version"] = self.identity_version_hash(identity_id, updated_at)
        payload.update(
            assertion=values.pop("assertion_hash"),
            attempt=values.pop("attempt_hash"),
            binding=values.pop("binding_hash"),
            iat=int(now.timestamp()),
            exp=int((now + PROOF_TTL).timestamp()),
            jti=values.pop("jti"),
        )
        if values:
            raise TypeError("unknown candidate proof field")
        return self._issue("candidate", payload)

    def issue_fresh_proof(self, **values) -> str:
        now = values.pop("now")
        updated_at = values.pop("identity_updated_at")
        identity_id = values.pop("identity_id")
        payload = {
            "purpose": "identity_link_fresh_proof",
            "iid": identity_id,
            "pid": values.pop("person_id"),
            "provider": values.pop("provider"),
            "version": self.identity_version_hash(identity_id, updated_at),
            "candidate": values.pop("candidate_jti"),
            "attempt": values.pop("attempt_hash"),
            "binding": values.pop("binding_hash"),
            "iat": int(now.timestamp()),
            "exp": int((now + PROOF_TTL).timestamp()),
            "jti": values.pop("jti"),
        }
        if values:
            raise TypeError("unknown fresh proof field")
        return self._issue("fresh", payload)

    def verify_candidate(self, token: str, now: datetime) -> CandidateProof:
        payload = self._verify("candidate", token, now)
        expected = {
            "purpose",
            "iid",
            "provider",
            "version",
            "assertion",
            "attempt",
            "binding",
            "iat",
            "exp",
            "jti",
        }
        if set(payload) != expected or payload["purpose"] != "identity_link_candidate":
            raise AuthenticationError("invalid identity-link proof")
        self._validate_common(payload)
        if any(
            not isinstance(payload[field], str) or len(payload[field]) != 64
            for field in ("version", "assertion")
        ):
            raise AuthenticationError("invalid identity-link proof")
        return CandidateProof(
            payload["iid"],
            payload["provider"],
            payload["version"],
            payload["assertion"],
            payload["attempt"],
            payload["binding"],
            payload["jti"],
        )

    def verify_fresh_proof(self, token: str, now: datetime) -> FreshIdentityProof:
        payload = self._verify("fresh", token, now)
        expected = {
            "purpose",
            "iid",
            "pid",
            "provider",
            "version",
            "candidate",
            "attempt",
            "binding",
            "iat",
            "exp",
            "jti",
        }
        if (
            set(payload) != expected
            or payload["purpose"] != "identity_link_fresh_proof"
        ):
            raise AuthenticationError("invalid identity-link proof")
        self._validate_common(payload)
        if (
            type(payload["pid"]) is not int
            or payload["pid"] == 0
            or not -MAX_POSTGRESQL_BIGINT - 1 <= payload["pid"] <= MAX_POSTGRESQL_BIGINT
            or not isinstance(payload["version"], str)
            or len(payload["version"]) != 64
            or not isinstance(payload["candidate"], str)
            or not 16 <= len(payload["candidate"]) <= 100
        ):
            raise AuthenticationError("invalid identity-link proof")
        return FreshIdentityProof(
            payload["iid"],
            payload["pid"],
            payload["provider"],
            payload["version"],
            payload["candidate"],
            payload["attempt"],
            payload["binding"],
            payload["jti"],
        )

    @staticmethod
    def validate_pair(*, candidate: CandidateProof, proof: FreshIdentityProof) -> None:
        if (
            candidate.jti != proof.candidate_jti
            or candidate.binding_hash != proof.binding_hash
            or candidate.provider == proof.provider
            or candidate.identity_id == proof.identity_id
        ):
            raise IdentityLinkConflict("identity-link proofs do not match")

    def _issue(self, domain: str, payload: dict) -> str:
        plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "ascii"
        )
        nonce = secrets.token_bytes(12)
        sealed = nonce + AESGCM(self._encryption_key).encrypt(
            nonce, plaintext, ("identity-link-proof:" + domain).encode("ascii")
        )
        return base64.urlsafe_b64encode(sealed).rstrip(b"=").decode("ascii")

    def _verify(self, domain: str, token: str, now: datetime) -> dict:
        try:
            if not isinstance(token, str) or not 80 <= len(token) <= 2048:
                raise ValueError
            sealed = base64.b64decode(
                token + "=" * (-len(token) % 4), altchars=b"-_", validate=True
            )
            if len(sealed) < 29:
                raise ValueError
            payload = json.loads(
                AESGCM(self._encryption_key).decrypt(
                    sealed[:12],
                    sealed[12:],
                    ("identity-link-proof:" + domain).encode("ascii"),
                )
            )
            timestamp = int(now.astimezone(timezone.utc).timestamp())
            if payload["iat"] > timestamp or payload["exp"] <= timestamp:
                raise ValueError
            return payload
        except (
            KeyError,
            TypeError,
            ValueError,
            UnicodeError,
            json.JSONDecodeError,
            InvalidTag,
        ):
            raise AuthenticationError(
                "invalid or expired identity-link proof"
            ) from None

    @staticmethod
    def _validate_common(payload: dict) -> None:
        if (
            type(payload["iid"]) is not int
            or payload["iid"] == 0
            or not -MAX_POSTGRESQL_BIGINT - 1 <= payload["iid"] <= MAX_POSTGRESQL_BIGINT
            or payload["provider"] not in PROVIDERS
            or not isinstance(payload["jti"], str)
            or not 16 <= len(payload["jti"]) <= 100
            or any(
                not isinstance(payload[field], str) or len(payload[field]) != 64
                for field in ("attempt", "binding")
            )
        ):
            raise AuthenticationError("invalid identity-link proof")


class IdentityLinkService:
    def __init__(
        self, repository, codec: IdentityLinkProofCodec, *, clock, recovery_auth=None
    ):
        self.repository, self.codec, self.clock = repository, codec, clock
        self.recovery_auth = recovery_auth

    @staticmethod
    def _hash(value: str) -> str:
        if not isinstance(value, str) or not value:
            raise AuthenticationError("identity-link field is required")
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def begin_candidate(
        self,
        *,
        provider: str,
        subject: str,
        raw_assertion: str,
        attempt_id: str,
        binding: str,
        display_name: str = "LINE 使用者",
    ) -> dict:
        now, request_nonce = self.clock(), secrets.token_urlsafe(18)
        if provider == "google":
            snapshot = self.repository.ensure_google_link_candidate(
                subject,
                f"identity-pending-{self._hash(provider + ':' + subject)[:32]}",
                now,
            )
        elif provider == "line":
            snapshot = self.repository.ensure_line_link_candidate(
                subject,
                display_name,
                f"identity-pending-{self._hash(provider + ':' + subject)[:32]}",
                now,
            )
        else:
            raise AuthenticationError("unsupported identity provider")
        if snapshot["status"] != "pending" or snapshot["person_id"] is not None:
            return (
                {"status": "already_linked"}
                if snapshot["status"] == "linked"
                else {"status": "unavailable"}
            )
        token = self.codec.issue_candidate(
            identity_id=snapshot["identity_id"],
            provider=provider,
            identity_updated_at=snapshot["updated_at"],
            assertion_hash=self._hash(raw_assertion),
            attempt_hash=self._hash(attempt_id),
            binding_hash=self._hash(binding),
            jti=request_nonce,
            now=now,
        )
        return {
            "status": "candidate_ready",
            "candidate_credential": token,
            "candidate_provider": provider,
            "expires_in": 300,
        }

    def issue_fresh_proof(
        self,
        *,
        candidate_credential: str,
        provider: str,
        subject: str,
        attempt_id: str,
        binding: str,
    ) -> dict:
        now = self.clock()
        candidate = self.codec.verify_candidate(candidate_credential, now)
        if candidate.binding_hash != self._hash(binding):
            raise IdentityLinkConflict("identity-link binding changed")
        snapshot = self.repository.linked_identity_for_proof(provider, subject, now)
        if snapshot["provider"] == candidate.provider:
            raise IdentityLinkConflict("a different login provider is required")
        token = self.codec.issue_fresh_proof(
            identity_id=snapshot["identity_id"],
            person_id=snapshot["person_id"],
            provider=snapshot["provider"],
            identity_updated_at=snapshot["updated_at"],
            candidate_jti=candidate.jti,
            attempt_hash=self._hash(attempt_id),
            binding_hash=self._hash(binding),
            jti=secrets.token_urlsafe(18),
            now=now,
        )
        return {
            "status": "proof_ready",
            "proof_credential": token,
            "candidate_provider": candidate.provider,
            "proof_provider": snapshot["provider"],
            "person": {"display_name": snapshot["display_name"]},
            "expires_in": 300,
        }

    def _confirm(
        self,
        *,
        candidate_credential: str,
        proof_credential: str,
        binding: str,
        outcome: str,
        current_person_id: int | None = None,
        platform: str | None = None,
        session_mode: str,
    ) -> dict:
        now = self.clock()
        candidate = self.codec.verify_candidate(candidate_credential, now)
        proof = self.codec.verify_fresh_proof(proof_credential, now)
        self.codec.validate_pair(candidate=candidate, proof=proof)
        if candidate.binding_hash != self._hash(binding):
            raise IdentityLinkConflict("identity-link binding changed")
        if outcome not in {"self_link", "recovery_link"}:
            raise IdentityLinkConflict("identity-link outcome is invalid")
        if outcome == "self_link" and current_person_id is None:
            raise IdentityLinkConflict("current session is required")
        recovery = None
        if session_mode not in {"mobile", "web"}:
            raise IdentityLinkConflict("trusted session mode is invalid")
        if outcome == "recovery_link" and session_mode == "mobile":
            if self.recovery_auth is None or platform not in {"ios", "android"}:
                raise InvalidArgument("recovery platform is required")
            refresh = self.recovery_auth.token_factory()
            recovery = {
                "refresh": refresh,
                "refresh_hash": secret_hash(refresh),
                "installation_id_hash": self._hash(binding),
                "platform": platform,
                "token_codec": self.recovery_auth.token_codec,
            }
        return self.repository.confirm_identity_link(
            candidate=candidate,
            proof=proof,
            codec=self.codec,
            now=now,
            outcome=outcome,
            current_person_id=current_person_id,
            recovery=recovery,
            session_mode=session_mode,
        )

    def confirm_mobile(self, **values) -> IdentityLinkResult:
        return self._confirm(session_mode="mobile", **values)

    def confirm_web(self, **values) -> IdentityLinkResult:
        values.pop("platform", None)
        return self._confirm(session_mode="web", platform=None, **values)
