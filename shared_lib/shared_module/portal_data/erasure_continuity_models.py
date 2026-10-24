"""Private append-only continuity metadata, never serialized as an API model."""

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from .models import SCHEMA, PortalDataBase

account_erasure_continuity_events = Table(
    "account_erasure_continuity_events",
    PortalDataBase.metadata,
    Column("operation_id", UUID(as_uuid=False), primary_key=True),
    Column("request_id", UUID(as_uuid=False), nullable=False),
    Column("target_kind", String(24), nullable=False),
    Column("expected_generation", UUID(as_uuid=False), nullable=False),
    Column("original_requested_at", DateTime(timezone=True), nullable=False),
    Column("original_receipt_hash", CHAR(64), nullable=False),
    Column("sequence", BigInteger, nullable=False),
    *(
        Column(name, DateTime(timezone=True), nullable=False)
        for name in (
            "previous_receipt_until",
            "previous_evidence_until",
            "receipt_until",
            "evidence_until",
            "occurred_at",
        )
    ),
    Column("operator_name", String(63), nullable=False),
    Column(
        "reason",
        String(32),
        nullable=False,
        server_default=text("'unfinished_request'"),
    ),
    UniqueConstraint("request_id", "sequence", name="uq_erasure_continuity_sequence"),
    CheckConstraint(
        "target_kind IN ('person','pending_identity')",
        name="ck_erasure_continuity_target",
    ),
    CheckConstraint(
        "original_receipt_hash ~ '^[0-9a-f]{64}$'", name="ck_erasure_continuity_hash"
    ),
    CheckConstraint("sequence>0", name="ck_erasure_continuity_sequence"),
    CheckConstraint("reason='unfinished_request'", name="ck_erasure_continuity_reason"),
    CheckConstraint(
        "isfinite(original_requested_at) AND isfinite(previous_receipt_until) "
        "AND isfinite(previous_evidence_until) AND isfinite(receipt_until) "
        "AND isfinite(evidence_until) AND isfinite(occurred_at) "
        "AND original_requested_at<=occurred_at AND occurred_at<previous_receipt_until "
        "AND previous_receipt_until<receipt_until AND previous_evidence_until<=evidence_until "
        "AND evidence_until>=receipt_until",
        name="ck_erasure_continuity_times",
    ),
    schema=SCHEMA,
)
