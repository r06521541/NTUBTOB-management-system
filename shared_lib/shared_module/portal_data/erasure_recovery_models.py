"""Core-only candidate0019 metadata; not runtime recovery authorization.

The authority pointer is deliberately not ORM mapped: older pinned schema tests
and runtimes must not SELECT a column absent before candidate0019. Migration
activation still requires coordinated deployment; metadata does not enable it.
"""

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    PrimaryKeyConstraint,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from .models import SCHEMA, PortalAuthorityStateRecord, PortalDataBase

account_erasure_admin_recovery_operations = Table(
    "account_erasure_admin_recovery_operations",
    PortalDataBase.metadata,
    Column("operation_id", UUID(as_uuid=False), nullable=False),
    Column(
        "job_id",
        UUID(as_uuid=False),
        ForeignKey(
            f"{SCHEMA}.account_erasure_jobs.id",
            name="fk_erasure_admin_recovery_job",
            ondelete="RESTRICT",
        ),
        nullable=True,
    ),
    Column("expected_generation", UUID(as_uuid=False), nullable=True),
    Column("scope_hash", CHAR(64), nullable=True),
    Column("expected_epoch", BigInteger, nullable=False),
    Column("applied_epoch", BigInteger, nullable=False),
    Column("operator_session_user", String(63), nullable=False),
    Column("applied_at", DateTime(timezone=True), nullable=False),
    Column("minimized_at", DateTime(timezone=True)),
    PrimaryKeyConstraint("operation_id", name="pk_erasure_admin_recovery"),
    UniqueConstraint("job_id", name="uq_erasure_admin_recovery_job"),
    CheckConstraint(
        "scope_hash ~ '^[0-9a-f]{64}$'", name="ck_erasure_recovery_scope_hash"
    ),
    CheckConstraint(
        "expected_epoch BETWEEN 1 AND 9223372036854775806",
        name="ck_erasure_recovery_expected_epoch",
    ),
    CheckConstraint(
        "applied_epoch = expected_epoch + 1", name="ck_erasure_recovery_applied_epoch"
    ),
    CheckConstraint("isfinite(applied_at)", name="ck_erasure_recovery_applied_at"),
    CheckConstraint(
        "(minimized_at IS NULL AND job_id IS NOT NULL AND expected_generation IS NOT NULL AND scope_hash IS NOT NULL) "
        "OR (minimized_at IS NOT NULL AND isfinite(minimized_at) AND minimized_at>=applied_at "
        "AND job_id IS NULL AND expected_generation IS NULL AND scope_hash IS NULL)",
        name="ck_erasure_recovery_minimized",
    ),
    schema=SCHEMA,
)

PortalAuthorityStateRecord.__table__.append_column(
    Column(
        "management_suspension_operation_id",
        UUID(as_uuid=False),
        ForeignKey(
            f"{SCHEMA}.account_erasure_admin_recovery_operations.operation_id",
            name="fk_authority_management_suspension",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
)
