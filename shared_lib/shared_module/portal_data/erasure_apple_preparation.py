"""Default-unused Apple preparation for the fixed fulfillment coordinators only.

Their _context_on must first revalidate the ORIGINAL sealed snapshot, current
full credential-row digests and workset on this same locked Connection. This
helper cannot establish those facts from job/item mappings alone, authorize an
operator, or replace the executor's acknowledged commit-before-I/O fence.

Use the existing acquisition cipher and the SAME trusted Apple client/custody
configuration. The existing Fernet token payload has no identity/generation AAD
or persisted client/key ID; do not infer such cryptographic provenance here.
No bootstrap import, environment/key lookup, new crypto, refresh, or persistence.
Only the returned one-shot callable may dispatch to the injected Apple revoker.
"""

import hmac
from collections.abc import Mapping
from threading import Lock
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..apple_token_revocation import AppleTokenRevoker
from ..mobile_api import secret_hash
from .erasure_fulfillment import _connection, _digest
from .erasure_person_fulfillment import PersonIdentitySnapshot
from .erasure_provider_execution import PreparedProviderEffect, _hash, _Rejected, _uuid


class ApplePreparationRejected(_Rejected):
    """Fixed scope/configuration failure; never supplied private values."""


class ApplePreparationUnavailable(RuntimeError):
    """Storage/preparation or consumed invocation; never permission to retry."""


def _reject():
    raise ApplePreparationRejected("apple_preparation_rejected") from None


def _identifier(value):
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        _reject()
    return value


def _database_uuid(value):
    if type(value) not in (str, UUID):
        _reject()
    return _uuid(str(value))


def _fields(value, names):
    if not isinstance(value, Mapping) or not set(names).issubset(value):
        _reject()


def _printable_ascii(value, maximum):
    return (
        type(value) is str
        and 1 <= len(value) <= maximum
        and value.isascii()
        and all(33 <= ord(char) <= 126 for char in value)
    )


def _effect(binding, scope, generation, action):
    # The closure retains only its action's minimal in-memory inputs, never SQL
    # objects. Consume before calling, including exceptions/unknown responses.
    lock = Lock()

    def invoke():
        nonlocal action
        with lock:
            if action is None:
                raise ApplePreparationUnavailable("apple_preparation_unavailable")
            current, action = action, None
        return current()

    return PreparedProviderEffect(binding, scope, generation, invoke)


class AppleErasurePreparation:
    """Local read-only preparation; no provider call until effect.invoke().

    provider_cipher is the existing SuccessorCipher open(bytes)->bytes port.
    client configuration must match original Apple acquisition; it is not read
    from a client request or guessed from an Apple subject. No callback here may
    acquire keys over a network. Failure to decode a PRESENT credential is manual
    attention, never absence; unsupported providers likewise are not success.
    """

    def __init__(self, *, provider_cipher, client_id, client_secret, revoker):
        if (
            not callable(getattr(provider_cipher, "open", None))
            or not _printable_ascii(client_id, 255)
            or not _printable_ascii(client_secret, 8192)
            or type(revoker) is not AppleTokenRevoker
        ):
            _reject()
        self._cipher = provider_cipher
        self._client_id, self._client_secret = client_id, client_secret
        self._revoker = revoker

    def __call__(self, connection, job, item, identity=None):
        try:
            _fields(
                job,
                (
                    "id",
                    "status",
                    "target_kind",
                    "person_id",
                    "auth_identity_id",
                    "expected_generation",
                    "scope_version",
                    "scope_hash",
                ),
            )
            _fields(
                item, ("id", "job_id", "stage", "binding_hash", "expected_generation")
            )
            job_id = _database_uuid(job["id"])
            _database_uuid(item["id"])
            generation = _database_uuid(job["expected_generation"])
            if (
                not isinstance(connection, Connection)
                or job["status"] not in {"verified", "processing", "needs_attention"}
                or type(job["scope_version"]) is not int
                or job["scope_version"] != 1
                or not _hash(job["scope_hash"])
                or _database_uuid(item["job_id"]) != job_id
                or item["stage"] != "provider_revocation"
                or _database_uuid(item["expected_generation"]) != generation
                or not _hash(item["binding_hash"])
            ):
                _reject()
            if job["target_kind"] == "pending_identity":
                if identity is not None or job["person_id"] is not None:
                    _reject()
                identifier = _identifier(job["auth_identity_id"])
                identity_generation, provider = generation, "apple"
                domain, label = "pending_item_v1", "provider"
            elif job["target_kind"] == "person":
                if (
                    type(identity) is not PersonIdentitySnapshot
                    or job["auth_identity_id"] is not None
                ):
                    _reject()
                _identifier(job["person_id"])
                identifier = _identifier(identity.identity_id)
                identity_generation = _uuid(identity.generation)
                provider = identity.provider
                if provider not in {"apple", "line", "google"} or not _hash(
                    identity.digest
                ):
                    _reject()
                domain, label = "person_item_v1", "provider:" + str(identifier)
            else:
                _reject()
            expected = _digest([domain, job_id, job["scope_hash"], label])
            if not hmac.compare_digest(expected, item["binding_hash"]):
                _reject()
            connection = _connection(connection)
            current = (
                connection.execute(
                    text(
                        "SELECT id,provider,person_id,status,account_generation::text AS generation,"
                        "encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS digest "
                        "FROM ntubtob.auth_identities t WHERE id=:id FOR UPDATE"
                    ),
                    {"id": identifier},
                )
                .mappings()
                .first()
            )
            _fields(
                current,
                ("id", "provider", "person_id", "status", "generation", "digest"),
            )
            if current["person_id"] is not None:
                _identifier(current["person_id"])
            if (
                _identifier(current["id"]) != identifier
                or current["provider"] != provider
                or current["person_id"] != job["person_id"]
                or current["generation"] != identity_generation
                or not _hash(current["digest"])
                or current["status"]
                not in (
                    {"pending", "disabled", "blocked"}
                    if identity is None
                    else {"linked", "disabled", "blocked"}
                )
                or (
                    identity is not None
                    and not hmac.compare_digest(current["digest"], identity.digest)
                )
            ):
                _reject()
            if provider != "apple":
                # No Apple row says nothing about LINE/Google consent or tokens.
                return _effect(
                    expected,
                    job["scope_hash"],
                    generation,
                    lambda: "manual_action_needed",
                )
            rows = (
                connection.execute(
                    text(
                        "SELECT id,auth_identity_id,encrypted_refresh_token,refresh_token_hash,status "
                        "FROM ntubtob.apple_provider_credentials WHERE auth_identity_id=:id FOR UPDATE"
                    ),
                    {"id": identifier},
                )
                .mappings()
                .all()
            )
            if len(rows) > 1:
                _reject()
            if not rows:
                # Only safe after the coordinator's same-TX snapshot validation.
                return _effect(
                    expected,
                    job["scope_hash"],
                    generation,
                    lambda: "credential_missing",
                )
            credential = rows[0]
            _fields(
                credential,
                (
                    "id",
                    "auth_identity_id",
                    "encrypted_refresh_token",
                    "refresh_token_hash",
                    "status",
                ),
            )
            _identifier(credential["id"])
            if _identifier(credential["auth_identity_id"]) != identifier or credential[
                "status"
            ] not in {"active", "revoked"}:
                _reject()
            token = self._token(credential)
            if token is None:
                return _effect(
                    expected,
                    job["scope_hash"],
                    generation,
                    lambda: "manual_action_needed",
                )
            # No Connection, row, subject or cipher is captured by the action.
            revoker, client_id, client_secret = (
                self._revoker,
                self._client_id,
                self._client_secret,
            )

            def dispatch():
                return revoker.revoke(
                    client_id=client_id, client_secret=client_secret, token=token
                )

            return _effect(expected, job["scope_hash"], generation, dispatch)
        except ApplePreparationRejected:
            raise
        except _Rejected:
            _reject()
        except Exception:
            raise ApplePreparationUnavailable("apple_preparation_unavailable") from None

    def _token(self, credential):
        # Failure of local key access/decryption/format is not an absent row.
        # Do not echo exceptions or retain a copy outside the prepared callable.
        try:
            encrypted = credential["encrypted_refresh_token"]
            if type(encrypted) is memoryview:
                if not 1 <= encrypted.nbytes <= 65536:
                    return None
                encrypted = encrypted.tobytes()
            if type(encrypted) is not bytes or not 1 <= len(encrypted) <= 65536:
                return None
            expected = credential["refresh_token_hash"]
            if not _hash(expected):
                return None
            plain = self._cipher.open(encrypted)
            if type(plain) is not bytes or not 1 <= len(plain) <= 16384:
                return None
            token = plain.decode("utf-8", errors="strict")
            if not _printable_ascii(token, 16384) or not hmac.compare_digest(
                secret_hash(token), expected
            ):
                return None
            return token
        except Exception:
            return None
