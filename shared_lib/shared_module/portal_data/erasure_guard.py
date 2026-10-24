"""Default-unused, transactional access gate for attached erasure jobs.

This is NOT authentication, fresh deletion proof, generation verification or a
deletion executor. Mobile has an explicit default-off integration seam; no runtime
composition enables it yet. Call before acquiring any
account/session/token row lock, inside the SAME transaction as the guarded write.
All lifecycle writers must follow ADMIN -> EVENT -> rows before enabling this gate;
in particular, never wrap a mutation that opens another Session while holding these
locks. Detached completed targets require a separate restore-suppression mechanism.
"""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .erasure_intake_routing import REVISION, unfiltered
from .runtime import acquire_admin_event_locks

BLOCKING_STATES = frozenset(
    {"verified", "processing", "needs_attention", "online_completed", "completed"}
)


class ErasureGuardUnavailable(RuntimeError):
    """A fixed diagnostic, without account identifiers or database details."""


class ErasureAccessBlocked(RuntimeError):
    """Attached erasure is in progress; not permission to retry or recreate."""


def require_account_not_erasing(
    session: Session, *, person_id: int | None = None, identity_id: int | None = None
) -> None:
    """Check Person and all its identities, or one still-unlinked identity.

    Requested-only jobs do not block: recording an intent is not verified deletion.
    Caller retains transaction ownership and must rollback on any exception. Uses
    one checked connection, never ORM routing/autoflush or a separate transaction.
    The optional identity must still resolve to the exact expected Person (or None
    for an unlinked target). Return None does not grant account/business access.
    """
    if (person_id is None and identity_id is None) or any(
        value is not None and (type(value) is not int or value <= 0)
        for value in (person_id, identity_id)
    ):
        raise ErasureGuardUnavailable("invalid_target")
    if not session.in_transaction() or session.new or session.dirty or session.deleted:
        raise ErasureGuardUnavailable("clean_transaction_required")
    try:
        connection = session.connection()
        driver = connection.connection.dbapi_connection
        if getattr(driver, "autocommit", None) is not False:
            raise ErasureGuardUnavailable("transaction_required")
        if connection.get_isolation_level() != "READ COMMITTED":
            # A snapshot established before waiting for the advisory lock could
            # miss a concurrently verified job under REPEATABLE READ.
            raise ErasureGuardUnavailable("read_committed_required")
        acquire_admin_event_locks(connection)
        revisions = tuple(
            connection.scalars(
                text("SELECT version_num FROM ntubtob.alembic_version")
            ).all()
        )
        if revisions not in (
            ("0014_account_erasure_ledger",),
            ("0015_account_generations",),
            ("0016_erasure_cancellation",),
            ("0017_erasure_work_items",),
            ("0018_erasure_privacy_mutation",),
            ("0019_erasure_admin_recovery",),
            ("0020_erasure_intake",),
            ("0021_erasure_continuity",),
            ("0022_erasure_retention",),
        ):
            raise ErasureGuardUnavailable("schema_not_ready")
        if (
            connection.scalar(
                text(
                    "SELECT pg_catalog.row_security_active('ntubtob.account_erasure_jobs'::pg_catalog.regclass)"
                )
            )
            is not False
        ):
            # Filtered ledger rows must never look like an account with no job.
            # This gate needs an already-authorized unfiltered backend view; it
            # never changes roles, disables RLS or grants itself access.
            raise ErasureGuardUnavailable("unfiltered_ledger_required")
        if (
            connection.scalar(
                text(
                    "SELECT pg_catalog.row_security_active('ntubtob.auth_identities'::pg_catalog.regclass)"
                )
            )
            is not False
        ):
            # The owned-identity subquery must not silently omit pending jobs.
            raise ErasureGuardUnavailable("unfiltered_identities_required")
        if identity_id is not None:
            identity = connection.execute(
                text(
                    "SELECT id, person_id FROM ntubtob.auth_identities WHERE id=:id FOR UPDATE"
                ),
                {"id": identity_id},
            ).first()
            if (
                identity is None
                or identity[0] != identity_id
                or identity[1] != person_id
            ):
                raise ErasureGuardUnavailable("identity_scope_changed")
        if person_id is not None:
            person = connection.scalar(
                text("SELECT id FROM ntubtob.people WHERE id=:id FOR UPDATE"),
                {"id": person_id},
            )
            if person != person_id:
                raise ErasureGuardUnavailable("person_scope_changed")
        rows = connection.execute(
            text(
                """
                SELECT status FROM ntubtob.account_erasure_jobs
                 WHERE person_id = :person_id
                    OR auth_identity_id = :identity_id
                    OR auth_identity_id IN (
                        SELECT id FROM ntubtob.auth_identities
                         WHERE person_id = :person_id
                    )
            """
            ),
            {"person_id": person_id, "identity_id": identity_id},
        ).all()
        if revisions == (REVISION,):
            unfiltered(connection)
            rows += connection.execute(
                text(
                    "SELECT status FROM ntubtob.account_erasure_intakes WHERE person_id=:person_id OR auth_identity_id=:identity_id OR auth_identity_id IN (SELECT id FROM ntubtob.auth_identities WHERE person_id=:person_id)"
                ),
                {"person_id": person_id, "identity_id": identity_id},
            ).all()
        for (status,) in rows:
            if status in BLOCKING_STATES:
                raise ErasureAccessBlocked("account_erasure_in_progress")
            if status != "requested":
                raise ErasureGuardUnavailable("unknown_erasure_state")
    except SQLAlchemyError:
        raise ErasureGuardUnavailable("guard_query_failed") from None
