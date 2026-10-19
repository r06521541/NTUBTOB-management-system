"""Pure legacy ownership planning; never a deletion authorization or executor.

Inputs must be a complete, consistent snapshot of candidate replies and referenced
members/users. This function cannot establish snapshot completeness or freshness.
A future transaction adapter must lock/revalidate the same scope before mutation.
No provider subject, message content, database connection or notification API is used.
"""

from dataclasses import dataclass
from typing import Iterable


class ErasureScopeRejected(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__("legacy erasure scope rejected: " + reason)


@dataclass(frozen=True)
class MemberReference:
    id: int
    person_id: int | None


@dataclass(frozen=True)
class LegacyIdentityReference:
    """Direct owner comes only from an exact LINE AuthIdentity database join."""

    id: int
    member_id: int | None
    direct_person_id: int | None = None


@dataclass(frozen=True)
class AttendanceReference:
    id: int
    person_id: int | None
    member_id: int | None
    user_id: int | None


@dataclass(frozen=True)
class LegacyErasureScope:
    member_ids: tuple[int, ...]
    line_user_ids: tuple[int, ...]
    reply_ids: tuple[int, ...]


def _identifier(value: int | None, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if type(value) is not int or value <= 0:
        raise ErasureScopeRejected("INVALID_IDENTIFIER")


def _unique_rows(rows: Iterable, expected_type: type, reference_fields: tuple):
    result = {}
    for row in rows:
        if type(row) is not expected_type:
            raise ErasureScopeRejected("INVALID_ROW")
        _identifier(row.id)
        for field in reference_fields:
            _identifier(getattr(row, field), optional=True)
        if row.id in result:
            raise ErasureScopeRejected("DUPLICATE_IDENTIFIER")
        result[row.id] = row
    return result


def plan_legacy_attendance_erasure(
    person_id: int,
    members: Iterable[MemberReference],
    identities: Iterable[LegacyIdentityReference],
    replies: Iterable[AttendanceReference],
) -> LegacyErasureScope:
    """Select proven ownership, rejecting ambiguity instead of unioning three keys.

    A direct Person-bound LINE AuthIdentity can prove legacy ownership without a
    Member. If both links exist they must agree; neither may hide a broken link.
    An unbound user is not inferred to belong to someone from a reply or nickname.
    Pending-identity erasure requires a separate proof-based scope.
    Ambiguous candidates, including unrelated ones supplied by the caller, stop the
    entire plan. This is conservative planning, not a request to scan live data.
    Returned IDs are internal and must not be logged or exposed as public evidence.
    """
    _identifier(person_id)
    member_rows = _unique_rows(members, MemberReference, ("person_id",))
    identity_rows = _unique_rows(
        identities, LegacyIdentityReference, ("member_id", "direct_person_id")
    )
    reply_rows = _unique_rows(
        replies, AttendanceReference, ("person_id", "member_id", "user_id")
    )

    def member_owner(member_id: int) -> int:
        member = member_rows.get(member_id)
        if member is None or member.person_id is None:
            raise ErasureScopeRejected("MEMBER_OWNER_UNRESOLVED")
        return member.person_id

    def identity_owner(user_id: int) -> int:
        identity = identity_rows.get(user_id)
        if identity is None:
            raise ErasureScopeRejected("LINE_OWNER_UNRESOLVED")
        owners = set()
        if identity.member_id is not None:
            owners.add(member_owner(identity.member_id))
        if identity.direct_person_id is not None:
            owners.add(identity.direct_person_id)
        if not owners:
            raise ErasureScopeRejected("LINE_OWNER_UNRESOLVED")
        if len(owners) != 1:
            raise ErasureScopeRejected("OWNERSHIP_CONFLICT")
        return owners.pop()

    selected_replies = []
    for row in reply_rows.values():
        owners = set()
        if row.person_id is not None:
            owners.add(row.person_id)
        if row.member_id is not None:
            owners.add(member_owner(row.member_id))
        if row.user_id is not None:
            owners.add(identity_owner(row.user_id))
        if not owners:
            raise ErasureScopeRejected("REPLY_OWNER_UNRESOLVED")
        if len(owners) != 1:
            raise ErasureScopeRejected("OWNERSHIP_CONFLICT")
        if person_id in owners:
            selected_replies.append(row.id)

    return LegacyErasureScope(
        tuple(
            sorted(row.id for row in member_rows.values() if row.person_id == person_id)
        ),
        tuple(
            sorted(
                row.id
                for row in identity_rows.values()
                if (row.member_id is not None or row.direct_person_id is not None)
                and identity_owner(row.id) == person_id
            )
        ),
        tuple(sorted(selected_replies)),
    )
