"""Private operator inventory observations; never a public/API model."""

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from .models import SCHEMA, PortalDataBase

account_erasure_backup_checks = Table(
    "account_erasure_backup_checks",
    PortalDataBase.metadata,
    Column("operation_id", UUID(as_uuid=False), primary_key=True),
    Column("request_id", UUID(as_uuid=False), nullable=False),
    Column("target_kind", String(24), nullable=False),
    Column("expected_generation", UUID(as_uuid=False), nullable=False),
    Column("original_requested_at", DateTime(timezone=True), nullable=False),
    Column("original_receipt_hash", CHAR(64), nullable=False),
    Column("sequence", BigInteger, nullable=False),
    Column("inventory_digest", CHAR(64), nullable=False),
    Column("checked_at", DateTime(timezone=True), nullable=False),
    Column("inventory_complete", Boolean, nullable=False),
    Column("last_restorable_until", DateTime(timezone=True)),
    Column("suppression_verified_at", DateTime(timezone=True)),
    Column("binding_readable", Boolean, nullable=False),
    Column("key_readable", Boolean, nullable=False),
    Column("operator_name", String(63), nullable=False),
    UniqueConstraint("request_id", "sequence", name="uq_erasure_backup_sequence"),
    CheckConstraint("sequence>0", name="ck_erasure_backup_sequence"),
    CheckConstraint(
        "target_kind IN ('person','pending_identity')", name="ck_erasure_backup_target"
    ),
    CheckConstraint(
        "original_receipt_hash ~ '^[0-9a-f]{64}$' AND inventory_digest ~ '^[0-9a-f]{64}$'",
        name="ck_erasure_backup_hashes",
    ),
    CheckConstraint(
        "isfinite(original_requested_at) AND isfinite(checked_at) AND checked_at>=original_requested_at AND (last_restorable_until IS NULL OR isfinite(last_restorable_until)) AND (suppression_verified_at IS NULL OR (isfinite(suppression_verified_at) AND suppression_verified_at BETWEEN original_requested_at AND checked_at))",
        name="ck_erasure_backup_times",
    ),
    Index("ix_erasure_backup_request_checked", "request_id", "checked_at"),
    schema=SCHEMA,
)

erasure_plan_delete_permits = Table(
    "erasure_plan_delete_permits",
    PortalDataBase.metadata,
    Column("backend", Integer, primary_key=True),
    Column("transaction_id", BigInteger, primary_key=True),
    Column("job_id", UUID(as_uuid=False), primary_key=True),
    Column("row_hash", CHAR(64), nullable=False),
    schema=SCHEMA,
)

account_erasure_plan_purges = Table(
    "account_erasure_plan_purges",
    PortalDataBase.metadata,
    Column("operation_id", UUID(as_uuid=False), primary_key=True),
    Column(
        "job_id",
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.account_erasure_jobs.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    ),
    Column("expected_generation", UUID(as_uuid=False), nullable=False),
    Column("scope_hash", CHAR(64), nullable=False),
    Column(
        "backup_operation_id",
        UUID(as_uuid=False),
        ForeignKey(
            f"{SCHEMA}.account_erasure_backup_checks.operation_id", ondelete="RESTRICT"
        ),
        nullable=False,
    ),
    Column("row_hash", CHAR(64), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("operator_name", String(63), nullable=False),
    CheckConstraint(
        "scope_hash ~ '^[0-9a-f]{64}$' AND row_hash ~ '^[0-9a-f]{64}$'",
        name="ck_erasure_plan_purge_hashes",
    ),
    CheckConstraint("isfinite(occurred_at)", name="ck_erasure_plan_purge_time"),
    schema=SCHEMA,
)
