"""Internal per-mutation suspension gate, never an authorization flag.

Before candidate0019 no suspension column exists. Explicit historical revisions
retain their previous behavior; this does not approve runtime rollout or permit
unknown schemas. Invoke at the clean transaction entry, before rows or replay.
Read/self-service and erasure receipt/cancel operations must not use this gate.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .erasure_management_guard import (
    REVISION,
    ManagementGuardUnavailable,
    require_management_writes_available,
)
from .runtime import acquire_admin_event_locks

LEGACY_REVISIONS = frozenset(
    {
        "0001_legacy_baseline",
        "0002_portal_data_foundation",
        "0003_legacy_bigint_activity_game",
        "0004_phase_c_identity_lifecycle",
        "0005_mobile_auth_api_foundation",
        "0006_staging_broker_operation_journal",
        "0007_mobile_notifications",
        "0008_mobile_notification_delivery",
        "0009_event_management_writes",
        "0010_apple_provider_lifecycle",
        "0011_event_notification_guest_lifecycle",
        "0012_persistent_admin_authority",
        "0013_account_deletion_requests",
        "0014_account_erasure_ledger",
        "0015_account_generations",
        "0016_erasure_cancellation",
        "0017_erasure_work_items",
        "0018_erasure_privacy_mutation",
    }
)


def require_management_mutation(session):
    """Check on the caller's connection; do not commit, flush or switch roles."""
    if (
        not isinstance(session, Session)
        or not session.in_transaction()
        or session.new
        or session.dirty
        or session.deleted
    ):
        raise ManagementGuardUnavailable("clean_transaction_required")
    try:
        connection = session.connection()
        if (
            not isinstance(connection, Connection)
            or connection.closed
            or not connection.in_transaction()
            or connection.get_isolation_level() != "READ COMMITTED"
            or getattr(connection.connection.dbapi_connection, "autocommit", None)
            is not False
        ):
            raise ManagementGuardUnavailable("transaction_required")
        acquire_admin_event_locks(connection)
        revisions = tuple(
            connection.scalars(
                text("SELECT version_num FROM ntubtob.alembic_version")
            ).all()
        )
        if revisions in (
            (REVISION,),
            ("0020_erasure_intake",),
            ("0021_erasure_continuity",),
            ("0022_erasure_retention",),
            ("0023_erasure_minimal_retention",),
            ("0024_erasure_provider_phases",),
        ):
            require_management_writes_available(connection)
        elif len(revisions) != 1 or revisions[0] not in LEGACY_REVISIONS:
            raise ManagementGuardUnavailable("schema_not_ready")
    except SQLAlchemyError:
        raise ManagementGuardUnavailable("authority_query_failed") from None
