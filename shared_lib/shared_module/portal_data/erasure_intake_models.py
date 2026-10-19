"""Private Core intake metadata: no placeholder execution scope or new policy."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
)
from sqlalchemy.dialects.postgresql import UUID

from .models import SCHEMA, PortalDataBase

account_erasure_intakes = Table(
    "account_erasure_intakes",
    PortalDataBase.metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("target_kind", String(16), nullable=False),
    Column(
        "person_id",
        BigInteger,
        ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT"),
        unique=True,
    ),
    Column(
        "auth_identity_id",
        BigInteger,
        ForeignKey(f"{SCHEMA}.auth_identities.id", ondelete="RESTRICT"),
        unique=True,
    ),
    Column("expected_generation", UUID(as_uuid=False), nullable=False),
    Column("status", String(16), nullable=False),
    Column("receipt_secret_hash", String(64), nullable=False),
    Column("retention_policy_version", Integer, nullable=False),
    *(
        Column(name, DateTime(timezone=True), nullable=False)
        for name in (
            "requested_at",
            "updated_at",
            "fulfillment_due_at",
            "receipt_expires_at",
            "evidence_expires_at",
        )
    ),
    Column("verified_at", DateTime(timezone=True)),
    Column("cancelled_at", DateTime(timezone=True)),
    Column(
        "materialized_job_id",
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.account_erasure_jobs.id", ondelete="RESTRICT"),
        unique=True,
    ),
    CheckConstraint(
        "status IN ('requested','verified','cancelled','materialized')",
        name="ck_erasure_intake_status",
    ),
    CheckConstraint(
        "target_kind IN ('person','pending_identity')", name="ck_erasure_intake_kind"
    ),
    CheckConstraint(
        "((status IN ('cancelled','materialized')) AND person_id IS NULL AND auth_identity_id IS NULL) OR (status IN ('requested','verified') AND ((target_kind='person' AND person_id IS NOT NULL AND auth_identity_id IS NULL) OR (target_kind='pending_identity' AND person_id IS NULL AND auth_identity_id IS NOT NULL)))",
        name="ck_erasure_intake_target",
    ),
    CheckConstraint(
        "receipt_secret_hash ~ '^[0-9a-f]{64}$' AND retention_policy_version>0",
        name="ck_erasure_intake_metadata",
    ),
    CheckConstraint(
        "isfinite(requested_at) AND isfinite(updated_at) AND isfinite(fulfillment_due_at) AND isfinite(receipt_expires_at) AND isfinite(evidence_expires_at) AND updated_at>=requested_at AND fulfillment_due_at>requested_at AND receipt_expires_at>requested_at AND evidence_expires_at>=GREATEST(fulfillment_due_at,receipt_expires_at)",
        name="ck_erasure_intake_times",
    ),
    CheckConstraint(
        "(verified_at IS NULL OR (isfinite(verified_at) AND verified_at>=requested_at AND verified_at<=updated_at)) AND (status NOT IN ('verified','materialized') OR verified_at IS NOT NULL) AND (status<>'requested' OR verified_at IS NULL)",
        name="ck_erasure_intake_verified",
    ),
    CheckConstraint(
        "(status='cancelled' AND cancelled_at IS NOT NULL AND isfinite(cancelled_at) AND cancelled_at>=requested_at AND cancelled_at<=updated_at) OR (status<>'cancelled' AND cancelled_at IS NULL)",
        name="ck_erasure_intake_cancelled",
    ),
    CheckConstraint(
        "(status='materialized' AND materialized_job_id IS NOT NULL AND materialized_job_id=id) OR (status<>'materialized' AND materialized_job_id IS NULL)",
        name="ck_erasure_intake_materialized",
    ),
    schema=SCHEMA,
)

account_erasure_intake_attempts = Table(
    "account_erasure_intake_attempts",
    PortalDataBase.metadata,
    Column("attempt_id", UUID(as_uuid=False), primary_key=True),
    Column(
        "intake_id",
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.account_erasure_intakes.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("assertion_binding", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("proof_expires_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "assertion_binding ~ '^[0-9a-f]{64}$'", name="ck_erasure_intake_attempt_binding"
    ),
    CheckConstraint(
        "isfinite(created_at) AND isfinite(proof_expires_at) AND proof_expires_at>created_at",
        name="ck_erasure_intake_attempt_times",
    ),
    schema=SCHEMA,
)
