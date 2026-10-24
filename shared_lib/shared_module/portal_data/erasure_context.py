"""Receipt-bound internal context lookup, not fresh proof or erasure permission.

Only a server-side challenge issuer should consume this DTO. Never serialize it
into a public response or log it. Holding a receipt secret permits context lookup,
not verification: a later fresh provider proof and locked generation recheck remain
mandatory. This reader performs no data mutation, job creation or provider call.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from hmac import compare_digest
from typing import Callable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..mobile_api import utc_now
from .erasure_continuity import ContinuityUnavailable, effective_expiry
from .erasure_intake_routing import receipt_table
from .runtime import acquire_admin_event_locks


class ErasureContextRejected(ValueError):
    """Fixed receipt/scope rejection without identifiers or supplied secrets."""


class ErasureContextUnavailable(RuntimeError):
    """Fixed transaction/storage error without driver or configuration details."""


@dataclass(frozen=True, repr=False)
class ErasureVerificationContext:
    job_id: str
    identity_id: int
    provider: str
    provider_subject: str
    identity_generation: str
    target_kind: str
    person_id: int | None
    target_generation: str
    requested_at: datetime


def _uuid(value: str) -> str:
    try:
        if type(value) is str and len(value) == 36 and str(UUID(value)) == value:
            return value
    except ValueError:
        pass
    raise ErasureContextRejected("context_scope_unavailable")


def _utc(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ErasureContextUnavailable("invalid_context_time")
    return value.astimezone(timezone.utc)


def load_erasure_verification_context(
    session: Session,
    *,
    job_id: str,
    receipt_secret: str,
    identity_id: int | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> ErasureVerificationContext:
    """Read one requested receipt's current target on a fixed locked connection.

    Receipt secrets are server-generated opaque URL-safe ASCII tokens of 32–256
    characters; bounds are not an entropy guarantee. Only their SHA-256 digest is
    compared with storage. The caller must begin a clean READ COMMITTED transaction
    before any account row locks and owns its commit/rollback. No returned context
    is authority to skip the later coordinator's fresh proof and generation checks.
    Without identity_id, only a pending-identity job can select its own stored
    identity. Person jobs still require a trusted caller's identity selector.
    """
    _uuid(job_id)
    if (
        (
            identity_id is not None
            and (type(identity_id) is not int or not 0 < identity_id <= 2**63 - 1)
        )
        or type(receipt_secret) is not str
        or not 32 <= len(receipt_secret) <= 256
        or re.fullmatch(r"[A-Za-z0-9_-]+", receipt_secret) is None
    ):
        raise ErasureContextRejected("receipt_unavailable")
    if not session.in_transaction() or session.new or session.dirty or session.deleted:
        raise ErasureContextUnavailable("clean_transaction_required")
    supplied_hash = hashlib.sha256(receipt_secret.encode("ascii")).hexdigest()
    try:
        connection = session.connection()
        if (
            getattr(connection.connection.dbapi_connection, "autocommit", None)
            is not False
        ):
            raise ErasureContextUnavailable("transaction_required")
        if connection.get_isolation_level() != "READ COMMITTED":
            raise ErasureContextUnavailable("read_committed_required")
        acquire_admin_event_locks(connection)
        revisions = tuple(
            connection.scalars(
                text("SELECT version_num FROM ntubtob.alembic_version")
            ).all()
        )
        if revisions not in (
            ("0015_account_generations",),
            ("0016_erasure_cancellation",),
            ("0017_erasure_work_items",),
            ("0018_erasure_privacy_mutation",),
            ("0019_erasure_admin_recovery",),
            ("0020_erasure_intake",),
            ("0021_erasure_continuity",),
        ):
            raise ErasureContextUnavailable("schema_not_ready")
        for table in ("account_erasure_jobs", "auth_identities", "people"):
            if (
                connection.scalar(
                    text(
                        f"SELECT pg_catalog.row_security_active('ntubtob.{table}'::pg_catalog.regclass)"
                    )
                )
                is not False
            ):
                raise ErasureContextUnavailable("unfiltered_tables_required")
        table = receipt_table(connection, job_id, revisions)
        job = (
            connection.execute(
                text(
                    "SELECT id,status,target_kind,person_id,auth_identity_id,expected_generation,"
                    "receipt_secret_hash,receipt_expires_at,evidence_expires_at,requested_at "
                    f"FROM ntubtob.{table} WHERE id=:id FOR UPDATE"
                ),
                {"id": job_id},
            )
            .mappings()
            .first()
        )
        if job is None or str(job["id"]) != job_id or job["status"] != "requested":
            raise ErasureContextRejected("receipt_unavailable")
        stored_hash = job["receipt_secret_hash"]
        if (
            type(stored_hash) is not str
            or re.fullmatch(r"[0-9a-f]{64}", stored_hash) is None
            or not compare_digest(stored_hash, supplied_hash)
        ):
            raise ErasureContextRejected("receipt_unavailable")
        if identity_id is None:
            if (
                job["target_kind"] != "pending_identity"
                or job["person_id"] is not None
                or type(job["auth_identity_id"]) is not int
                or not 0 < job["auth_identity_id"] <= 2**63 - 1
            ):
                raise ErasureContextRejected("context_scope_unavailable")
            identity_id = job["auth_identity_id"]
        identity = (
            connection.execute(
                text(
                    "SELECT id,provider,provider_subject,person_id,status,account_generation "
                    "FROM ntubtob.auth_identities WHERE id=:id FOR UPDATE"
                ),
                {"id": identity_id},
            )
            .mappings()
            .first()
        )
        if (
            identity is None
            or identity["id"] != identity_id
            or type(identity["status"]) is not str
        ):
            raise ErasureContextRejected("context_scope_unavailable")
        identity_generation = _uuid(str(identity["account_generation"]))
        target_kind, person_id = job["target_kind"], job["person_id"]
        if target_kind == "person":
            if (
                type(person_id) is not int
                or person_id <= 0
                or job["auth_identity_id"] is not None
                or identity["person_id"] != person_id
                or identity["status"] not in {"linked", "disabled", "blocked"}
            ):
                raise ErasureContextRejected("context_scope_unavailable")
            person = (
                connection.execute(
                    text(
                        "SELECT id,account_generation FROM ntubtob.people WHERE id=:id FOR UPDATE"
                    ),
                    {"id": person_id},
                )
                .mappings()
                .first()
            )
            if person is None or person["id"] != person_id:
                raise ErasureContextRejected("context_scope_unavailable")
            generation = _uuid(str(person["account_generation"]))
        elif target_kind == "pending_identity":
            if (
                person_id is not None
                or job["auth_identity_id"] != identity_id
                or identity["person_id"] is not None
                or identity["status"] not in {"pending", "disabled", "blocked"}
            ):
                raise ErasureContextRejected("context_scope_unavailable")
            generation = identity_generation
        else:
            raise ErasureContextRejected("context_scope_unavailable")
        if (
            generation != str(job["expected_generation"])
            or type(identity["provider"]) is not str
            or identity["provider"] not in {"line", "apple", "google"}
            or type(identity["provider_subject"]) is not str
            or not 1 <= len(identity["provider_subject"]) <= 255
        ):
            raise ErasureContextRejected("context_scope_unavailable")
        # Identity/Person row locks may have waited too; check expiry afterwards.
        try:
            now = _utc(clock())
        except Exception:
            raise ErasureContextUnavailable("invalid_context_time") from None
        requested_at = _utc(job["requested_at"])
        if (
            effective_expiry(connection, job, "receipt_expires_at", revisions=revisions)
            <= now
            or requested_at > now
        ):
            raise ErasureContextRejected("receipt_unavailable")
        return ErasureVerificationContext(
            job_id=job_id,
            identity_id=identity_id,
            provider=identity["provider"],
            provider_subject=identity["provider_subject"],
            identity_generation=identity_generation,
            target_kind=target_kind,
            person_id=person_id,
            target_generation=generation,
            requested_at=requested_at,
        )
    except (SQLAlchemyError, ContinuityUnavailable):
        raise ErasureContextUnavailable("context_read_unavailable") from None
