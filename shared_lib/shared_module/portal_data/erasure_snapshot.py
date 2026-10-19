"""Internal read-only legacy snapshot; not a full account inventory or executor."""

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..account_erasure_scope import (
    AttendanceReference,
    ErasureScopeRejected,
    LegacyErasureScope,
    LegacyIdentityReference,
    MemberReference,
    plan_legacy_attendance_erasure,
)
from .models import AuthIdentityRecord as AuthIdentity
from .models import LegacyGameAttendanceReplyRecord as Reply
from .models import LegacyLineUserRecord as LineUser
from .models import LegacyMemberRecord as Member


def legacy_attendance_snapshot(session: Session, person_id: int) -> LegacyErasureScope:
    """Read one consistent snapshot without returning names or provider subjects.

    Caller must authorize the target and open REPEATABLE READ/SERIALIZABLE first.
    A returned plan cannot be reused as deletion authority: future mutation must
    establish lifecycle guards, drain writers and revalidate a fresh scope.
    Both legacy Member and exact Person-bound LINE AuthIdentity links are checked.
    Disabled/blocked identities still identify their bound Person, not permission.
    Pending user ownership and other account stores require separate adapters.
    """
    if type(person_id) is not int or person_id <= 0:
        raise ErasureScopeRejected("INVALID_IDENTIFIER")
    if not session.in_transaction():
        raise ErasureScopeRejected("SNAPSHOT_TRANSACTION_REQUIRED")
    try:
        connection = session.connection()
        driver = connection.connection.dbapi_connection
        if getattr(driver, "autocommit", None) is not False:
            raise ErasureScopeRejected("SNAPSHOT_AUTOCOMMIT_REJECTED")
        if connection.get_isolation_level() not in {
            "REPEATABLE READ",
            "SERIALIZABLE",
        }:
            raise ErasureScopeRejected("SNAPSHOT_ISOLATION_REQUIRED")
        with session.no_autoflush:
            members = [
                MemberReference(*row)
                for row in connection.execute(
                    select(Member.id, Member.person_id).where(
                        Member.person_id == person_id
                    )
                ).all()
            ]
            owned_member_ids = {row.id for row in members}
            # Join subjects only within SQL; never project them into the plan.
            # The provider predicate prevents Apple/Google subject collisions.
            user_keys = select(
                LineUser.id, LineUser.member_id, AuthIdentity.person_id
            ).outerjoin(
                AuthIdentity,
                and_(
                    AuthIdentity.provider == "line",
                    AuthIdentity.provider_subject == LineUser.line_user_id,
                ),
            )
            users = [
                LegacyIdentityReference(*row)
                for row in connection.execute(
                    user_keys.where(
                        or_(
                            LineUser.member_id.in_(owned_member_ids),
                            AuthIdentity.person_id == person_id,
                        )
                    )
                ).all()
            ]
            owned_user_ids = {row.id for row in users}
            replies = [
                AttendanceReference(*row)
                for row in connection.execute(
                    select(
                        Reply.id, Reply.person_id, Reply.member_id, Reply.user_id
                    ).where(
                        or_(
                            Reply.person_id == person_id,
                            Reply.member_id.in_(owned_member_ids),
                            Reply.user_id.in_(owned_user_ids),
                        )
                    )
                ).all()
            ]
            # OR is only candidate discovery. Every populated key must agree in
            # the pure planner; missing references are not silently discarded.
            referenced_user_ids = {
                row.user_id for row in replies if row.user_id is not None
            }
            users.extend(
                LegacyIdentityReference(*row)
                for row in connection.execute(
                    user_keys.where(
                        LineUser.id.in_(referenced_user_ids - owned_user_ids)
                    )
                ).all()
            )
            referenced_member_ids = {
                row.member_id for row in replies + users if row.member_id is not None
            }
            members.extend(
                MemberReference(*row)
                for row in connection.execute(
                    select(Member.id, Member.person_id).where(
                        Member.id.in_(referenced_member_ids - owned_member_ids)
                    )
                ).all()
            )
            return plan_legacy_attendance_erasure(person_id, members, users, replies)
    except SQLAlchemyError:
        raise ErasureScopeRejected("SNAPSHOT_READ_FAILED") from None
