"""Private cleanup control metadata, not a per-target tombstone or API payload."""

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Integer,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import OID

from .models import SCHEMA, PortalDataBase

erasure_evidence_delete_permits = Table(
    "erasure_evidence_delete_permits",
    PortalDataBase.metadata,
    Column("backend", Integer, primary_key=True),
    Column("transaction_id", BigInteger, primary_key=True),
    Column("table_oid", OID, primary_key=True),
    Column("row_key", Text, primary_key=True),
    Column("operation", String(6), nullable=False),
    Column("old_hash", CHAR(64), nullable=False),
    Column("new_hash", CHAR(64)),
    CheckConstraint(
        "operation IN ('delete','update')", name="ck_erasure_evidence_permit_action"
    ),
    schema=SCHEMA,
)

erasure_retention_state = Table(
    "erasure_retention_state",
    PortalDataBase.metadata,
    Column("singleton_id", Integer, primary_key=True),
    Column("cleanup_performed", Boolean, nullable=False, server_default=text("false")),
    CheckConstraint("singleton_id=1", name="ck_erasure_retention_singleton"),
    schema=SCHEMA,
)
