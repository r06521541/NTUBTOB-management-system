"""Default-unused immutable work bindings and append-only outcome evidence.

The binding hash must come from a reviewed exact scope inventory, not raw private
identifiers. A generation match against the job is not fresh entity authorization.
Neither a model import nor a recorded start dispatches I/O. The caller must commit
the irreversible job fence and started event before any external operation.
Unknown is not retry permission; only one explicit reconciliation is representable.
Evidence custody/disposal and complete fulfillment are outside these models.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .erasure_models import AccountErasureJobRecord
from .models import SCHEMA, PortalDataBase


class AccountErasureItemRecord(PortalDataBase):
    __tablename__ = "account_erasure_items"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "stage", "binding_hash", name="uq_erasure_item_binding"
        ),
        CheckConstraint(
            "stage IN ('provider_revocation', 'online_erasure', 'manual_redaction', 'restore_suppression')",
            name="ck_erasure_item_stage",
        ),
        CheckConstraint(
            "binding_hash ~ '^[0-9a-f]{64}$'", name="ck_erasure_item_binding"
        ),
        CheckConstraint("isfinite(created_at)", name="ck_erasure_item_time"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey(AccountErasureJobRecord.id, ondelete="RESTRICT"),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    binding_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_generation: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AccountErasureItemEventRecord(PortalDataBase):
    __tablename__ = "account_erasure_item_events"
    __table_args__ = (
        UniqueConstraint(
            "item_id", "event_sequence", name="uq_erasure_item_event_sequence"
        ),
        CheckConstraint(
            "event_sequence > 0 AND event_sequence <= 3",
            name="ck_erasure_item_event_sequence",
        ),
        CheckConstraint("isfinite(occurred_at)", name="ck_erasure_item_event_time"),
        CheckConstraint(
            "(event_sequence = 1 AND event_kind = 'started' AND result_code = 'in_progress') OR "
            "(event_sequence IN (2, 3) AND event_kind = 'confirmed' AND result_code IN ('succeeded', 'credential_missing', 'manual_action_needed', 'not_applicable')) OR "
            "(event_sequence = 2 AND event_kind = 'unknown' AND result_code = 'response_unknown') OR "
            "(event_sequence IN (2, 3) AND event_kind = 'failed' AND result_code IN ('scope_conflict', 'dependency_unavailable', 'verification_failed'))",
            name="ck_erasure_item_event_result",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    item_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey(AccountErasureItemRecord.id, ondelete="RESTRICT"),
        nullable=False,
    )
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    result_code: Mapped[str] = mapped_column(String(24), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
