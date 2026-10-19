"""Default-unused erasure evidence schema, not an authorization or executor.

expected_generation alone is not authorization. Candidate0015 stores immutable
account generations; the default-unused verification coordinator rechecks them
against trusted fresh proof. Deadlines are explicit metadata, not approved retention
policy or permission to delete evidence automatically. Importing this module registers
the tables; runtime composition does not enable erasure fulfillment. Candidate0016
adds terminal cancellation and a monotonic dispatch fence, not permission to cancel
or to restore sessions. Retaining downgrade does not make old runtimes compatible.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from . import erasure_intake_models  # Register additive Core intake metadata.
from .models import SCHEMA, PortalDataBase

# Core-only private custody: never put encrypted snapshots in an ORM repr.
# Retention metadata remains solely on the immutable parent job.
account_erasure_sealed_plans = Table(
    "account_erasure_sealed_plans",
    PortalDataBase.metadata,
    Column(
        "job_id",
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.account_erasure_jobs.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column("key_id", String(64), nullable=False),
    Column("ciphertext", LargeBinary, nullable=False),
    CheckConstraint(
        "key_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'", name="ck_erasure_plan_key"
    ),
    CheckConstraint(
        "octet_length(ciphertext) BETWEEN 52 AND 4194355", name="ck_erasure_plan_size"
    ),
    schema=SCHEMA,
)


class AccountErasureJobRecord(PortalDataBase):
    __tablename__ = "account_erasure_jobs"
    __table_args__ = (
        CheckConstraint(
            "target_kind IN ('person', 'pending_identity')",
            name="ck_erasure_job_target_kind",
        ),
        CheckConstraint(
            "status IN ('requested', 'verified', 'processing', 'needs_attention', 'online_completed', 'completed', 'cancelled')",
            name="ck_erasure_job_status",
        ),
        CheckConstraint(
            "(status <> 'cancelled' AND target_kind = 'person' AND person_id IS NOT NULL AND auth_identity_id IS NULL) OR "
            "(status <> 'cancelled' AND target_kind = 'pending_identity' AND auth_identity_id IS NOT NULL AND person_id IS NULL) OR "
            "(status IN ('online_completed', 'completed', 'cancelled') AND person_id IS NULL AND auth_identity_id IS NULL)",
            name="ck_erasure_job_target",
        ),
        CheckConstraint("scope_version > 0", name="ck_erasure_job_scope_version"),
        CheckConstraint(
            "scope_hash ~ '^[0-9a-f]{64}$'", name="ck_erasure_job_scope_hash"
        ),
        CheckConstraint(
            "receipt_secret_hash ~ '^[0-9a-f]{64}$'", name="ck_erasure_job_receipt_hash"
        ),
        CheckConstraint(
            "retention_policy_version > 0", name="ck_erasure_job_policy_version"
        ),
        CheckConstraint(
            "isfinite(fulfillment_due_at) AND isfinite(receipt_expires_at) AND isfinite(evidence_expires_at) AND "
            "fulfillment_due_at > requested_at AND receipt_expires_at > requested_at AND "
            "evidence_expires_at >= receipt_expires_at AND evidence_expires_at >= fulfillment_due_at",
            name="ck_erasure_job_deadlines",
        ),
        CheckConstraint(
            "isfinite(requested_at) AND isfinite(updated_at) AND "
            "isfinite(COALESCE(verified_at, requested_at)) AND "
            "isfinite(COALESCE(online_completed_at, requested_at)) AND "
            "isfinite(COALESCE(completed_at, requested_at)) AND "
            "isfinite(COALESCE(cancelled_at, requested_at)) AND "
            "isfinite(COALESCE(irreversible_started_at, requested_at)) AND "
            "updated_at >= requested_at AND "
            "(verified_at IS NULL OR (verified_at >= requested_at AND verified_at <= updated_at)) AND "
            "(irreversible_started_at IS NULL OR (irreversible_started_at >= verified_at AND irreversible_started_at <= updated_at)) AND "
            "(online_completed_at IS NULL OR (online_completed_at >= verified_at AND online_completed_at >= irreversible_started_at AND online_completed_at <= updated_at)) AND "
            "(completed_at IS NULL OR (completed_at >= online_completed_at AND completed_at <= updated_at)) AND "
            "(cancelled_at IS NULL OR (cancelled_at >= requested_at AND (verified_at IS NULL OR cancelled_at >= verified_at) AND cancelled_at <= updated_at))",
            name="ck_erasure_job_times",
        ),
        CheckConstraint(
            "(status = 'requested' AND verified_at IS NULL) OR "
            "(status NOT IN ('requested', 'cancelled') AND verified_at IS NOT NULL) OR status = 'cancelled'",
            name="ck_erasure_job_verified",
        ),
        CheckConstraint(
            "(status = 'cancelled' AND cancelled_at IS NOT NULL) OR (status <> 'cancelled' AND cancelled_at IS NULL)",
            name="ck_erasure_job_cancelled",
        ),
        CheckConstraint(
            "(irreversible_started_at IS NULL OR status NOT IN ('requested', 'cancelled')) AND "
            "(status NOT IN ('online_completed', 'completed') OR irreversible_started_at IS NOT NULL)",
            name="ck_erasure_job_irreversible",
        ),
        CheckConstraint(
            "(status IN ('online_completed', 'completed') AND online_completed_at IS NOT NULL) OR "
            "(status NOT IN ('online_completed', 'completed') AND online_completed_at IS NULL)",
            name="ck_erasure_job_online_completed",
        ),
        CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL) OR (status <> 'completed' AND completed_at IS NULL)",
            name="ck_erasure_job_completed",
        ),
        Index(
            "uq_erasure_job_person",
            "person_id",
            unique=True,
            postgresql_where=text("person_id IS NOT NULL"),
        ),
        Index(
            "uq_erasure_job_identity",
            "auth_identity_id",
            unique=True,
            postgresql_where=text("auth_identity_id IS NOT NULL"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    target_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    person_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.people.id", ondelete="RESTRICT")
    )
    auth_identity_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.auth_identities.id", ondelete="RESTRICT")
    )
    expected_generation: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_version: Mapped[int] = mapped_column(Integer, nullable=False)
    scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    receipt_secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    retention_policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    irreversible_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    online_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    fulfillment_due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    receipt_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    evidence_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AccountErasureRequestAttemptRecord(PortalDataBase):
    """Opaque immutable intent binding, not fresh proof or deletion permission.

    No target FK or provider subject: cancellation/target erasure cannot rebind a
    consumed attempt. Evidence disposal shares the job's controlled cleanup gate.
    """

    __tablename__ = "account_erasure_request_attempts"
    __table_args__ = (
        CheckConstraint(
            "assertion_binding ~ '^[0-9a-f]{64}$'",
            name="ck_erasure_attempt_binding",
        ),
        CheckConstraint(
            "isfinite(created_at) AND isfinite(proof_expires_at) AND "
            "proof_expires_at > created_at AND "
            "EXTRACT(EPOCH FROM (proof_expires_at - created_at)) <= 300",
            name="ck_erasure_attempt_times",
        ),
        {"schema": SCHEMA},
    )
    attempt_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.account_erasure_jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assertion_binding: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    proof_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AccountErasureStepRecord(PortalDataBase):
    """Append-only events; unknown is evidence, never an implicit retry permit."""

    __tablename__ = "account_erasure_steps"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "stage", "attempt", "event_sequence", name="uq_erasure_step_event"
        ),
        CheckConstraint(
            "stage IN ('verification', 'access_block', 'provider_revocation', 'online_erasure', 'online_verification', 'restore_suppression', 'completion', 'cancellation')",
            name="ck_erasure_step_stage",
        ),
        CheckConstraint(
            "attempt > 0 AND event_sequence > 0", name="ck_erasure_step_sequence"
        ),
        CheckConstraint("isfinite(occurred_at)", name="ck_erasure_step_time"),
        CheckConstraint(
            "(event_kind = 'planned' AND result_code = 'scheduled') OR "
            "(event_kind = 'started' AND result_code = 'in_progress') OR "
            "(event_kind = 'confirmed' AND result_code IN ('succeeded', 'credential_missing', 'manual_action_needed', 'not_applicable')) OR "
            "(event_kind = 'unknown' AND result_code = 'response_unknown') OR "
            "(event_kind = 'failed' AND result_code IN ('scope_conflict', 'dependency_unavailable', 'verification_failed'))",
            name="ck_erasure_step_result",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.account_erasure_jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    result_code: Mapped[str] = mapped_column(String(24), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
