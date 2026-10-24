"""Default-unused receipt context and fresh-proof cancellation, never reactivation.

The injected proof verifier is local only. Provider I/O must finish before opening
the caller-owned transaction. Successful return is not a durable commit receipt.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hmac import compare_digest
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..erasure_cancellation_proof import CancellationContext, FreshCancellationProof
from ..mobile_api import utc_now
from .erasure_continuity import ContinuityUnavailable, effective_expiry
from .erasure_intake_routing import INTAKES, receipt_table
from .runtime import acquire_admin_event_locks


class ErasureCancellationRejected(ValueError):
    """Fixed rejection without private input or target details."""


class ErasureCancellationUnavailable(RuntimeError):
    """Storage/configuration uncertainty, not retry authorization."""


@dataclass(frozen=True)
class CancelledErasureRequest:
    job_id: str
    cancelled_at: datetime


def _reject():
    raise ErasureCancellationRejected("cancellation_unavailable")


def _uuid(value):
    try:
        if type(value) is str and str(UUID(value)) == value:
            return value
    except ValueError:
        pass
    _reject()


def _instant(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        _reject()
    return value.astimezone(timezone.utc)


def _connection(session):
    if not session.in_transaction() or session.new or session.dirty or session.deleted:
        raise ErasureCancellationUnavailable("clean_transaction_required")
    connection = session.connection()
    if (
        getattr(connection.connection.dbapi_connection, "autocommit", None) is not False
        or connection.get_isolation_level() != "READ COMMITTED"
    ):
        raise ErasureCancellationUnavailable("read_committed_transaction_required")
    acquire_admin_event_locks(connection)
    if tuple(
        connection.scalars(
            text("SELECT version_num FROM ntubtob.alembic_version")
        ).all()
    ) not in (
        ("0016_erasure_cancellation",),
        ("0017_erasure_work_items",),
        ("0018_erasure_privacy_mutation",),
        ("0019_erasure_admin_recovery",),
        ("0020_erasure_intake",),
        ("0021_erasure_continuity",),
    ):
        raise ErasureCancellationUnavailable("schema_not_ready")
    for table in (
        "account_erasure_jobs",
        "account_erasure_steps",
        "people",
        "auth_identities",
    ):
        if (
            connection.scalar(
                text(
                    f"SELECT pg_catalog.row_security_active('ntubtob.{table}'::pg_catalog.regclass)"
                )
            )
            is not False
        ):
            raise ErasureCancellationUnavailable("unfiltered_tables_required")
    return connection


def _now(clock):
    try:
        return _instant(clock())
    except Exception:
        raise ErasureCancellationUnavailable("invalid_cancellation_clock") from None


def _row(connection, sql, **params):
    return connection.execute(text(sql), params).mappings().first()


def _job(connection, job_id):
    _uuid(job_id)
    table = receipt_table(connection, job_id)
    fence = (
        "NULL::timestamptz AS irreversible_started_at"
        if table == INTAKES
        else "irreversible_started_at"
    )
    job = _row(
        connection,
        "SELECT id,target_kind,person_id,auth_identity_id,expected_generation,status,"
        f"{fence},requested_at,updated_at,receipt_expires_at,evidence_expires_at,receipt_secret_hash "
        f"FROM ntubtob.{table} WHERE id=:id FOR UPDATE",
        id=job_id,
    )
    if (
        job is None
        or str(job["id"]) != job_id
        or job["status"]
        not in {"requested", "verified", "processing", "needs_attention"}
        or job["irreversible_started_at"] is not None
    ):
        _reject()
    _uuid(str(job["expected_generation"]))
    return job


def _target(connection, job):
    if job["target_kind"] == "person":
        if (
            type(job["person_id"]) is not int
            or job["person_id"] <= 0
            or job["auth_identity_id"] is not None
        ):
            _reject()
        target = _row(
            connection,
            "SELECT id,account_generation FROM ntubtob.people WHERE id=:id FOR UPDATE",
            id=job["person_id"],
        )
    elif job["target_kind"] == "pending_identity":
        if (
            type(job["auth_identity_id"]) is not int
            or job["auth_identity_id"] <= 0
            or job["person_id"] is not None
        ):
            _reject()
        target = _row(
            connection,
            "SELECT id,account_generation,person_id,status FROM ntubtob.auth_identities WHERE id=:id FOR UPDATE",
            id=job["auth_identity_id"],
        )
        if target is not None and (
            target["person_id"] is not None
            or target["status"] not in {"pending", "disabled", "blocked"}
        ):
            _reject()
    else:
        _reject()
    if target is None or str(target["account_generation"]) != str(
        job["expected_generation"]
    ):
        _reject()


def _fresh_job(connection, job, now):
    if (
        _instant(job["requested_at"]) > now
        or _instant(job["updated_at"]) > now
        or effective_expiry(connection, job, "receipt_expires_at") <= now
    ):
        _reject()


def load_cancellation_context(session, *, job_id, receipt_secret, clock=utc_now):
    """Receipt authorizes context only, never cancellation without fresh proof."""
    if (
        type(receipt_secret) is not str
        or not 32 <= len(receipt_secret) <= 256
        or re.fullmatch(r"[A-Za-z0-9_-]+", receipt_secret) is None
    ):
        _reject()
    try:
        connection = _connection(session)
        job = _job(connection, job_id)
        stored = job["receipt_secret_hash"]
        if (
            type(stored) is not str
            or re.fullmatch(r"[0-9a-f]{64}", stored) is None
            or not compare_digest(
                stored, hashlib.sha256(receipt_secret.encode("ascii")).hexdigest()
            )
        ):
            _reject()
        _target(connection, job)
        _fresh_job(connection, job, _now(clock))
        return CancellationContext(
            job_id,
            job["target_kind"],
            str(job["expected_generation"]),
            job["requested_at"],
        )
    except (SQLAlchemyError, ContinuityUnavailable):
        raise ErasureCancellationUnavailable(
            "cancellation_context_unavailable"
        ) from None


class ErasureCancellationCoordinator:
    def __init__(self, *, verifier, audience, max_proof_age, clock=utc_now):
        if (
            not callable(verifier)
            or type(audience) is not str
            or not 1 <= len(audience) <= 200
            or type(max_proof_age) is not timedelta
            or not timedelta(0) < max_proof_age <= timedelta(minutes=5)
            or not callable(clock)
        ):
            raise ErasureCancellationUnavailable("invalid_configuration")
        self.verifier, self.audience, self.max_proof_age, self.clock = (
            verifier,
            audience,
            max_proof_age,
            clock,
        )

    def cancel(self, session, *, job_id, assertion):
        _uuid(job_id)
        if type(assertion) is not str or not 1 <= len(assertion) <= 4096:
            _reject()
        try:
            connection = _connection(session)
            job = _job(connection, job_id)
            try:
                proof = self.verifier(assertion)
            except Exception:
                raise ErasureCancellationRejected(
                    "cancellation_proof_rejected"
                ) from None
            if (
                type(proof) is not FreshCancellationProof
                or proof.job_id != job_id
                or proof.purpose != "account_erasure_cancellation"
                or proof.audience != self.audience
                or proof.target_kind != job["target_kind"]
                or proof.target_generation != str(job["expected_generation"])
                or type(proof.provider) is not str
                or proof.provider not in {"line", "apple", "google"}
                or type(proof.provider_subject) is not str
                or not 1 <= len(proof.provider_subject) <= 255
            ):
                _reject()
            identity = _row(
                connection,
                "SELECT id,provider,provider_subject,person_id,status,account_generation "
                "FROM ntubtob.auth_identities WHERE provider=:provider AND provider_subject=:subject FOR UPDATE",
                provider=proof.provider,
                subject=proof.provider_subject,
            )
            if (
                identity is None
                or identity["provider"] != proof.provider
                or identity["provider_subject"] != proof.provider_subject
            ):
                _reject()
            _uuid(str(identity["account_generation"]))
            if job["target_kind"] == "person":
                if identity["person_id"] != job["person_id"] or identity[
                    "status"
                ] not in {"linked", "disabled", "blocked"}:
                    _reject()
            elif (
                identity["id"] != job["auth_identity_id"]
                or identity["person_id"] is not None
                or identity["status"] not in {"pending", "disabled", "blocked"}
            ):
                _reject()
            _target(connection, job)
            now = _now(self.clock)
            _fresh_job(connection, job, now)
            issued, authenticated, expires = map(
                _instant, (proof.issued_at, proof.authenticated_at, proof.expires_at)
            )
            if (
                issued < _instant(job["requested_at"])
                or not issued <= authenticated <= now < expires
                or now - issued > self.max_proof_age
                or expires - issued > self.max_proof_age
            ):
                _reject()
            with connection.begin_nested():
                table = receipt_table(connection, job_id)
                fence = (
                    "" if table == INTAKES else "AND irreversible_started_at IS NULL "
                )
                result = connection.execute(
                    text(
                        f"UPDATE ntubtob.{table} SET status='cancelled',cancelled_at=:now,updated_at=:now,"
                        f"person_id=NULL,auth_identity_id=NULL WHERE id=:id {fence}"
                        "AND status IN ('requested','verified','processing','needs_attention')"
                    ),
                    dict(id=job_id, now=now),
                )
                if result.rowcount != 1:
                    _reject()
                if table != INTAKES:
                    connection.execute(
                        text(
                            "INSERT INTO ntubtob.account_erasure_steps "
                            "(job_id,stage,attempt,event_sequence,event_kind,result_code,occurred_at) "
                            "VALUES (:id,'cancellation',1,1,'confirmed','succeeded',:now)"
                        ),
                        dict(id=job_id, now=now),
                    )
            return CancelledErasureRequest(job_id, now)
        except (SQLAlchemyError, ContinuityUnavailable):
            raise ErasureCancellationUnavailable(
                "cancellation_storage_unavailable"
            ) from None
