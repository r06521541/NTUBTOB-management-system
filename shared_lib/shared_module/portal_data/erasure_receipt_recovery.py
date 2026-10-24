"""Default-unused live-target receipt recovery, not login or a new request.

The injected trusted verifier decrypts local, dedicated-purpose proof only; all
provider I/O must finish before this call. The dedicated codec is not wired to any
public API or native flow. A proof may repeat this read within its original five-minute window;
it is NOT single-use. Recovered receipts keep their original expiry and authority.

Only an attached current target is recoverable. Freshness is not historical
ownership: current immutable generation/FKs AND proof issuance strictly after the
request and current identity/Person timestamps are required. Equal timestamps or
intervening profile/remap updates conservatively reject. This relies on trusted
server timestamps, not a client timestamp or a historical subject index. Deleted
targets with all original factors lost cannot recover here. No rows are mutated.
"""

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..erasure_recovery_proof import RECEIPT_RECOVERY_PURPOSE, FreshReceiptRecoveryProof
from ..mobile_api import utc_now
from .erasure_continuity import effective_expiry
from .erasure_intake_routing import target_row
from .runtime import acquire_admin_event_locks

_LIVE_STATES = frozenset({"requested", "verified", "processing", "needs_attention"})
_REVISIONS = frozenset(
    {
        ("0015_account_generations",),
        ("0016_erasure_cancellation",),
        ("0017_erasure_work_items",),
        ("0018_erasure_privacy_mutation",),
        ("0019_erasure_admin_recovery",),
        ("0020_erasure_intake",),
        ("0021_erasure_continuity",),
        ("0022_erasure_retention",),
    }
)


class ReceiptRecoveryRejected(ValueError):
    """Fixed unavailable response; no subject, secret or target-existence detail."""


class ReceiptRecoveryUnavailable(RuntimeError):
    """Fixed infrastructure boundary failure; never a new-request instruction."""


@dataclass(frozen=True, repr=False)
class RecoveredErasureReceipt:
    """Internal result, not the existing requested-only public request DTO."""

    job_id: str
    receipt_secret: str
    status: str
    requested_at: datetime
    updated_at: datetime
    receipt_expires_at: datetime


def _reject():
    raise ReceiptRecoveryRejected("receipt_recovery_unavailable") from None


def _utc(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        _reject()
    return value.astimezone(timezone.utc)


def _uuid(value):
    if type(value) not in (str, UUID):
        _reject()
    result = str(UUID(str(value)))
    if str(value) != result:
        _reject()
    return result


class ReceiptRecoveryRepository:
    def __init__(self, engine, key, *, verifier, audience, clock=utc_now):
        if (
            not isinstance(engine, Engine)
            or engine.dialect.name != "postgresql"
            or type(key) is not bytes
            or len(key) < 32
            or not callable(verifier)
            or not callable(clock)
            or type(audience) is not str
            or not 1 <= len(audience) <= 200
        ):
            raise ReceiptRecoveryRejected("invalid_recovery_configuration")
        self.engine, self._key = engine, key
        self.verifier, self.audience, self.clock = verifier, audience, clock

    def _fresh(self, proof):
        issued, authenticated, expiry = (
            _utc(proof.issued_at),
            _utc(proof.authenticated_at),
            _utc(proof.expires_at),
        )
        now = _utc(self.clock())
        if not issued <= authenticated <= now < expiry or expiry - issued > timedelta(
            minutes=5
        ):
            _reject()
        return now

    def _proof(self, credential):
        if type(credential) is not str or not 80 <= len(credential) <= 4096:
            _reject()
        try:
            proof = self.verifier(credential)
        except Exception:
            raise ReceiptRecoveryUnavailable("recovery_verifier_unavailable") from None
        if (
            type(proof) is not FreshReceiptRecoveryProof
            or type(proof.purpose) is not str
            or proof.purpose != RECEIPT_RECOVERY_PURPOSE
            or type(proof.audience) is not str
            or proof.audience != self.audience
            or type(proof.provider) is not str
            or proof.provider not in {"apple", "google", "line"}
            or type(proof.provider_subject) is not str
            or not 1 <= len(proof.provider_subject) <= 255
            or not proof.provider_subject.strip()
        ):
            _reject()
        return proof, self._fresh(proof)

    def recover(self, verified_credential):
        """Reissue the SAME receipt, without creating an attempt or changing state.

        The verifier is server-injected local code, not an arbitrary caller hook.
        Fixed diagnostic codes must be translated without echoing credentials.
        No secret is returned before transaction exit succeeds.
        """
        try:
            proof, started_at = self._proof(verified_credential)
            with Session(self.engine) as session, session.begin():
                if (
                    not session.in_transaction()
                    or session.new
                    or session.dirty
                    or session.deleted
                ):
                    raise ReceiptRecoveryUnavailable("clean_transaction_required")
                connection = session.connection()
                if (
                    getattr(connection.connection.dbapi_connection, "autocommit", None)
                    is not False
                    or connection.get_isolation_level() != "READ COMMITTED"
                ):
                    raise ReceiptRecoveryUnavailable(
                        "read_committed_transaction_required"
                    )
                acquire_admin_event_locks(connection)
                revisions = tuple(
                    connection.scalars(
                        text("SELECT version_num FROM ntubtob.alembic_version")
                    ).all()
                )
                if revisions not in _REVISIONS:
                    raise ReceiptRecoveryUnavailable("schema_not_ready")
                for table in ("auth_identities", "people", "account_erasure_jobs"):
                    if (
                        connection.scalar(
                            text(
                                f"SELECT pg_catalog.row_security_active('ntubtob.{table}'::regclass)"
                            )
                        )
                        is not False
                    ):
                        raise ReceiptRecoveryUnavailable("unfiltered_tables_required")

                def row(sql, **params):
                    return (
                        connection.execute(text(sql), params).mappings().one_or_none()
                    )

                identity = row(
                    "SELECT id,person_id,status,account_generation,created_at,updated_at "
                    "FROM ntubtob.auth_identities WHERE provider=:provider AND provider_subject=:subject FOR UPDATE",
                    provider=proof.provider,
                    subject=proof.provider_subject,
                )
                if (
                    identity is None
                    or type(identity["id"]) is not int
                    or identity["id"] <= 0
                ):
                    _reject()
                person_id = identity["person_id"]
                current_rows = [identity]
                if person_id is None:
                    if identity["status"] not in {"pending", "disabled", "blocked"}:
                        _reject()
                    kind, column, target = (
                        "pending_identity",
                        "auth_identity_id",
                        identity["id"],
                    )
                    generation = _uuid(identity["account_generation"])
                else:
                    if (
                        type(person_id) is not int
                        or person_id <= 0
                        or identity["status"] not in {"linked", "disabled", "blocked"}
                    ):
                        _reject()
                    person = row(
                        "SELECT id,account_generation,created_at,updated_at FROM ntubtob.people WHERE id=:id FOR UPDATE",
                        id=person_id,
                    )
                    if (
                        person is None
                        or type(person["id"]) is not int
                        or person["id"] != person_id
                    ):
                        _reject()
                    current_rows.append(person)
                    kind, column, target = "person", "person_id", person_id
                    generation = _uuid(person["account_generation"])
                job = target_row(
                    connection,
                    column,
                    target,
                    "id,target_kind,person_id,auth_identity_id,expected_generation,status,"
                    "requested_at,updated_at,receipt_secret_hash,receipt_expires_at,evidence_expires_at ",
                    revisions,
                )
                if (
                    job is None
                    or job["status"] not in _LIVE_STATES
                    or job["target_kind"] != kind
                    or job[column] != target
                    or job[
                        (
                            "person_id"
                            if kind == "pending_identity"
                            else "auth_identity_id"
                        )
                    ]
                    is not None
                    or _uuid(job["expected_generation"]) != generation
                ):
                    _reject()
                requested, updated, deadline = (
                    _utc(job["requested_at"]),
                    _utc(job["updated_at"]),
                    effective_expiry(
                        connection, job, "receipt_expires_at", revisions=revisions
                    ),
                )
                # Strictly later issuance prevents an old subject-only proof from
                # binding a rebuilt account/job or a later remap into an older job.
                issue_floor = [requested]
                for current in current_rows:
                    created, changed = _utc(current["created_at"]), _utc(
                        current["updated_at"]
                    )
                    if changed < created:
                        _reject()
                    issue_floor.extend((created, changed))
                if max(issue_floor) >= _utc(proof.issued_at):
                    _reject()
                now = self._fresh(proof)
                if now < started_at or not requested <= updated <= now < deadline:
                    _reject()
                job_id = _uuid(job["id"])
                # Existing request receipt bytes, not a new proof/key derivation.
                secret = hmac.new(
                    self._key,
                    b"ntubtob:account-erasure:receipt:v1\x00" + UUID(job_id).bytes,
                    hashlib.sha256,
                ).hexdigest()
                stored_hash = job["receipt_secret_hash"]
                if (
                    type(stored_hash) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", stored_hash) is None
                    or not hmac.compare_digest(
                        stored_hash, hashlib.sha256(secret.encode("ascii")).hexdigest()
                    )
                ):
                    _reject()
                result = RecoveredErasureReceipt(
                    job_id, secret, job["status"], requested, updated, deadline
                )
            finished_at = self._fresh(proof)
            if finished_at < now or finished_at >= deadline:
                _reject()
            return result
        except (ReceiptRecoveryRejected, ReceiptRecoveryUnavailable):
            raise
        except Exception:
            raise ReceiptRecoveryUnavailable(
                "receipt_recovery_storage_unavailable"
            ) from None
