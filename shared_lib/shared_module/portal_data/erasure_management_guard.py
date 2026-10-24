"""Default-unused readers for candidate0019 operational suspension.

Call on the SAME clean transaction/connection as a management mutation, before
row locks or DML. This is not authentication or a generic permission grant. The
operation reader is internal only and never replaces account-erasure scope checks.
Database owners/superusers are outside the isolated-role authority boundary.
No connection, credential lookup, network, approval, resume or promotion occurs.
"""

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from .runtime import acquire_admin_event_locks

REVISION = "0019_erasure_admin_recovery"


class ManagementGuardUnavailable(RuntimeError):
    """Fixed inability to establish management authority; not permission."""


class ManagementWritesSuspended(RuntimeError):
    """Durable operational suspension requires a separate controlled recovery."""


@dataclass(frozen=True, repr=False)
class AppliedAdminSuspension:
    operation_id: str
    job_id: str
    generation: str
    scope_hash: str
    authority_epoch: int


def _unavailable(reason):
    raise ManagementGuardUnavailable(reason) from None


def _uuid(value):
    try:
        if type(value) is str and len(value) == 36 and str(UUID(value)) == value:
            return value
    except ValueError:
        pass
    _unavailable("invalid_binding")


def _state(connection):
    if (
        not isinstance(connection, Connection)
        or connection.closed
        or not connection.in_transaction()
        or connection.get_isolation_level() != "READ COMMITTED"
        or getattr(connection.connection.dbapi_connection, "autocommit", None)
        is not False
    ):
        _unavailable("transaction_required")
    acquire_admin_event_locks(connection)
    if tuple(
        connection.scalars(text("SELECT version_num FROM ntubtob.alembic_version"))
    ) not in (
        (REVISION,),
        ("0020_erasure_intake",),
        ("0021_erasure_continuity",),
        ("0022_erasure_retention",),
        ("0023_erasure_minimal_retention",),
    ):
        _unavailable("schema_not_ready")
    for table in (
        "portal_authority_state",
        "account_erasure_admin_recovery_operations",
    ):
        if (
            connection.scalar(
                text(
                    f"SELECT pg_catalog.row_security_active('ntubtob.{table}'::regclass)"
                )
            )
            is not False
        ):
            _unavailable("unfiltered_authority_required")
    rows = connection.execute(
        text(
            "SELECT singleton_id,mode,epoch,management_suspension_operation_id::text "
            "FROM ntubtob.portal_authority_state ORDER BY singleton_id FOR UPDATE"
        )
    ).all()
    if (
        len(rows) != 1
        or type(rows[0][0]) is not int
        or rows[0][0] != 1
        or rows[0][1] != "persistent"
        or type(rows[0][2]) is not int
        or not 1 <= rows[0][2] <= 2**63 - 1
    ):
        _unavailable("authority_state_unavailable")
    return rows[0][2:]


def require_management_writes_available(connection):
    """Reject suspension without consulting or changing App login/receipt state."""
    try:
        _, operation_id = _state(connection)
        if operation_id is not None:
            # Even malformed/missing evidence may never reopen management writes.
            raise ManagementWritesSuspended("management_writes_suspended")
    except SQLAlchemyError:
        _unavailable("authority_query_failed")


def read_applied_admin_suspension(connection, *, job_id, generation, scope_hash):
    """Read exact durable approval under canonical locks; never consume/reapply.

    Caller must separately lock/revalidate the current job and original target
    inventory before irreversible work. A returned DTO is not a public bearer token.
    No wall-clock expiry can implicitly clear an already committed suspension.
    """
    _uuid(job_id)
    _uuid(generation)
    if type(scope_hash) is not str or re.fullmatch(r"[0-9a-f]{64}", scope_hash) is None:
        _unavailable("invalid_binding")
    try:
        epoch, operation_id = _state(connection)
        _uuid(operation_id)
        rows = connection.execute(
            text(
                "SELECT operation_id::text,job_id::text,expected_generation::text,"
                "scope_hash,expected_epoch,applied_epoch "
                "FROM ntubtob.account_erasure_admin_recovery_operations "
                "WHERE operation_id=CAST(:operation AS uuid) FOR SHARE"
            ),
            {"operation": operation_id},
        ).all()
        if (
            len(rows) != 1
            or tuple(rows[0][:4]) != (operation_id, job_id, generation, scope_hash)
            or type(rows[0][4]) is not int
            or type(rows[0][5]) is not int
            or not 1 <= rows[0][4] < 2**63 - 1
            or rows[0][5] != rows[0][4] + 1
            or rows[0][5] != epoch
        ):
            _unavailable("suspension_binding_unavailable")
        return AppliedAdminSuspension(
            operation_id, job_id, generation, scope_hash, epoch
        )
    except SQLAlchemyError:
        _unavailable("authority_query_failed")
