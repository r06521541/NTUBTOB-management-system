"""Confidential receipt-only reconciliation; no login or target dependency.

This default-unused reader returns stored status, not proof that erasure succeeded.
It never creates requests, changes deadlines, verifies identity or writes evidence.
The caller owns the database transaction and must keep receipt secrets out of logs.
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

_STATUSES = frozenset(
    {
        "requested",
        "verified",
        "processing",
        "needs_attention",
        "online_completed",
        "completed",
    }
)


class ErasureReceiptRejected(ValueError):
    """Fixed receipt rejection with no supplied secret or existence details."""


class ErasureReceiptUnavailable(RuntimeError):
    """Fixed storage/transaction failure with no driver details."""


@dataclass(frozen=True, repr=False)
class ErasureReceiptStatus:
    job_id: str
    status: str
    requested_at: datetime
    updated_at: datetime


def _valid_job_id(value: str) -> bool:
    try:
        return type(value) is str and len(value) == 36 and str(UUID(value)) == value
    except ValueError:
        return False


def _utc(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ErasureReceiptUnavailable("invalid_receipt_time")
    return value.astimezone(timezone.utc)


def load_erasure_receipt(
    session: Session,
    *,
    job_id: str,
    receipt_secret: str,
    clock: Callable[[], datetime] = utc_now,
) -> ErasureReceiptStatus:
    """Read minimal status using a receipt, even after sessions/targets are gone.

    Requires a clean active READ COMMITTED SQL transaction, not a login principal.
    Only the fixed checked connection is used; canonical locks precede the job row.
    Receipt possession is not permission for cancellation or another mutation.
    """
    if (
        not _valid_job_id(job_id)
        or type(receipt_secret) is not str
        or not 32 <= len(receipt_secret) <= 256
        or re.fullmatch(r"[A-Za-z0-9_-]+", receipt_secret) is None
    ):
        raise ErasureReceiptRejected("receipt_unavailable")
    if not session.in_transaction() or session.new or session.dirty or session.deleted:
        raise ErasureReceiptUnavailable("clean_transaction_required")
    supplied_hash = hashlib.sha256(receipt_secret.encode("ascii")).hexdigest()
    try:
        connection = session.connection()
        if (
            getattr(connection.connection.dbapi_connection, "autocommit", None)
            is not False
        ):
            raise ErasureReceiptUnavailable("transaction_required")
        if connection.get_isolation_level() != "READ COMMITTED":
            raise ErasureReceiptUnavailable("read_committed_required")
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
            ("0022_erasure_retention",),
        ):
            raise ErasureReceiptUnavailable("schema_not_ready")
        if (
            connection.scalar(
                text(
                    "SELECT pg_catalog.row_security_active('ntubtob.account_erasure_jobs'::pg_catalog.regclass)"
                )
            )
            is not False
        ):
            raise ErasureReceiptUnavailable("unfiltered_ledger_required")
        table = receipt_table(connection, job_id, revisions)
        job = (
            connection.execute(
                text(
                    "SELECT id,status,target_kind,expected_generation,requested_at,updated_at,receipt_secret_hash,receipt_expires_at,evidence_expires_at "
                    f"FROM ntubtob.{table} WHERE id=:id FOR UPDATE"
                ),
                {"id": job_id},
            )
            .mappings()
            .first()
        )
        if job is None or str(job["id"]) != job_id:
            raise ErasureReceiptRejected("receipt_unavailable")
        stored_hash = job["receipt_secret_hash"]
        if (
            type(stored_hash) is not str
            or re.fullmatch(r"[0-9a-f]{64}", stored_hash) is None
            or not compare_digest(stored_hash, supplied_hash)
        ):
            raise ErasureReceiptRejected("receipt_unavailable")
        # A receipt may expire while waiting for either the advisory or row locks.
        try:
            now = _utc(clock())
        except Exception:
            raise ErasureReceiptUnavailable("invalid_receipt_time") from None
        if (
            effective_expiry(connection, job, "receipt_expires_at", revisions=revisions)
            <= now
        ):
            raise ErasureReceiptRejected("receipt_unavailable")
        status = job["status"]
        known_statuses = _STATUSES | (
            {"cancelled"}
            if revisions
            in (
                ("0016_erasure_cancellation",),
                ("0017_erasure_work_items",),
                ("0018_erasure_privacy_mutation",),
                ("0019_erasure_admin_recovery",),
                ("0020_erasure_intake",),
                ("0021_erasure_continuity",),
                ("0022_erasure_retention",),
            )
            else set()
        )
        if type(status) is not str or status not in known_statuses:
            raise ErasureReceiptUnavailable("unknown_erasure_state")
        requested_at, updated_at = _utc(job["requested_at"]), _utc(job["updated_at"])
        if updated_at < requested_at:
            raise ErasureReceiptUnavailable("invalid_receipt_time")
        return ErasureReceiptStatus(job_id, status, requested_at, updated_at)
    except (SQLAlchemyError, ContinuityUnavailable):
        raise ErasureReceiptUnavailable("receipt_read_unavailable") from None
