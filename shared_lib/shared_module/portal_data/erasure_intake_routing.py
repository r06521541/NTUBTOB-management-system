"""Fixed receipt routing under the caller's canonical transaction locks.

Never query missing candidate tables on a historical revision. A materialized
intake delegates to its FK-bound job; cancelled intake remains receipt-readable.
These helpers grant no proof, authentication, review or execution authority.
"""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

REVISION = "0020_erasure_intake"
INTAKES = "account_erasure_intakes"
JOBS = "account_erasure_jobs"


def enabled(connection, revisions=None):
    if revisions is None:
        revisions = tuple(
            connection.scalars(text("SELECT version_num FROM ntubtob.alembic_version"))
        )
    return tuple(revisions) in {
        (REVISION,),
        ("0021_erasure_continuity",),
        ("0022_erasure_retention",),
    }


def unfiltered(connection, table=INTAKES):
    if table not in (INTAKES, "account_erasure_intake_attempts"):
        raise SQLAlchemyError("intake_table_rejected")
    if (
        connection.scalar(
            text(f"SELECT pg_catalog.row_security_active('ntubtob.{table}'::regclass)")
        )
        is not False
    ):
        raise SQLAlchemyError("unfiltered_intake_required")


def receipt_table(connection, job_id, revisions=None):
    if not enabled(connection, revisions):
        return JOBS
    unfiltered(connection)
    intake = connection.execute(
        text(
            f"SELECT status,materialized_job_id FROM ntubtob.{INTAKES} WHERE id=:id FOR UPDATE"
        ),
        {"id": job_id},
    ).first()
    if intake is None:
        return JOBS
    if intake[0] == "materialized":
        if str(intake[1]) != str(job_id):
            raise SQLAlchemyError("intake_materialization_unavailable")
        return JOBS
    if intake[0] not in {"requested", "verified", "cancelled"}:
        raise SQLAlchemyError("intake_state_unavailable")
    return INTAKES


def target_row(connection, column, target, columns, revisions=None):
    # SQL fields are repository constants, never public input. The only dynamic
    # ownership selector is this fixed allowlist.
    if column not in {"person_id", "auth_identity_id"}:
        raise SQLAlchemyError("intake_target_rejected")
    tables = (JOBS,)
    if enabled(connection, revisions):
        unfiltered(connection)
        tables += (INTAKES,)
    found = []
    for table in tables:
        row = (
            connection.execute(
                text(
                    f"SELECT {columns} FROM ntubtob.{table} WHERE {column}=:id FOR UPDATE"
                ),
                {"id": target},
            )
            .mappings()
            .one_or_none()
        )
        if row is not None:
            found.append(row)
    if len(found) > 1:
        raise SQLAlchemyError("intake_target_conflict")
    return found[0] if found else None
