from __future__ import annotations

import copy
import threading
from collections import Counter
from datetime import datetime, timezone
from typing import Iterable, Protocol

from sqlalchemy import Engine, and_, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .domain import (
    ACCESS_LEVELS,
    ATTENDANCE_REPLIES,
    IDENTITY_PROVIDERS,
    PORTAL_STATUSES,
    QUALIFICATIONS,
    AuthIdentity,
    AuthorizationError,
    BackfillSummary,
    ConflictError,
    Invitee,
    Person,
    is_qualification_active,
    require_choice,
    require_reason,
    validate_guest_period,
)
from .models import (
    AccessAuditRecord,
    AuthIdentityRecord,
    EventAttendanceReplyRecord,
    EventAuditRecord,
    EventEligibilityRuleRecord,
    EventInviteeOverrideRecord,
    EventInviteeRecord,
    EventRecord,
    LegacyMemberRecord,
    PersonQualificationRecord,
    PersonRecord,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _category_for(qualification: str) -> str:
    return qualification if qualification in QUALIFICATIONS else "other"


class TeamPortalRepository(Protocol):
    def create_person(
        self,
        display_name: str,
        access_level: str = "basic",
        status: str = "active",
        member_id: int | None = None,
        qualifications: Iterable[str] = (),
        guest_valid_from: datetime | None = None,
        guest_valid_until: datetime | None = None,
    ) -> Person: ...

    def create_pending_identity(self, provider: str, subject: str) -> AuthIdentity: ...
    def identities_for_person(self, person_id: int) -> list[AuthIdentity]: ...
    def qualifications_for_person(self, person_id: int) -> set[str]: ...
    def get_person(self, person_id: int) -> Person: ...

    def grant_qualification(
        self,
        person_id: int,
        qualification: str,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> None: ...

    def revoke_qualification(self, person_id: int, qualification: str) -> None: ...

    def approve_identity(
        self,
        actor_id: int,
        identity_id: int,
        reason: str,
        request_id: str,
        person_id: int | None = None,
        display_name: str | None = None,
        member_id: int | None = None,
        qualifications: Iterable[str] = (),
        guest_valid_from: datetime | None = None,
        guest_valid_until: datetime | None = None,
    ) -> Person: ...

    def block_identity(
        self, actor_id: int, identity_id: int, reason: str, request_id: str
    ) -> AuthIdentity: ...

    def change_access(
        self,
        actor_id: int,
        target_id: int,
        access_level: str,
        reason: str,
        request_id: str,
    ) -> Person: ...

    def change_status(
        self, actor_id: int, target_id: int, status: str, reason: str, request_id: str
    ) -> Person: ...

    def create_event(
        self,
        actor_id: int,
        title: str,
        event_type: str,
        start_at: datetime,
        eligibility: Iterable[str],
    ) -> int: ...

    def publish_event(
        self, actor_id: int, event_id: int, request_id: str
    ) -> list[Invitee]: ...

    def set_invitee_override(
        self,
        actor_id: int,
        event_id: int,
        person_id: int,
        action: str,
        participation_category: str,
        reason: str,
    ) -> None: ...

    def event_invitees(self, event_id: int) -> list[Invitee]: ...
    def reply_to_event(self, event_id: int, person_id: int, reply: str) -> None: ...
    def roster_summary(self, event_id: int) -> dict[str, int]: ...

    def backfill_members(
        self, fake_admin_member_ids: Iterable[int] = ()
    ) -> BackfillSummary: ...


class InMemoryTeamPortalRepository:
    """Single fake repository used by local demo/domain tests; not a table mock."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._next_ids = Counter()
        self.people: dict[int, Person] = {}
        self.members: dict[int, int | None] = {}
        self.member_names: dict[int, str] = {}
        self.identities: dict[int, AuthIdentity] = {}
        self.identity_keys: dict[tuple[str, str], int] = {}
        self.qualifications: dict[tuple[int, str], dict] = {}
        self.audits: list[dict] = []
        self.audit_requests: set[str] = set()
        self.events: dict[int, dict] = {}
        self.overrides: dict[tuple[int, int], dict] = {}
        self.invitees: dict[tuple[int, int], Invitee] = {}
        self.replies: dict[tuple[int, int], str] = {}

    def _next(self, kind: str) -> int:
        self._next_ids[kind] += 1
        return self._next_ids[kind]

    def _require_admin(self, person_id: int) -> Person:
        person = self.get_person(person_id)
        if not person.is_admin:
            raise AuthorizationError("active admin required")
        return person

    def _require_event_manager(self, person_id: int) -> Person:
        person = self.get_person(person_id)
        if not person.can_manage_events:
            raise AuthorizationError("active officer or admin required")
        return person

    def get_person(self, person_id: int) -> Person:
        person = self.people.get(person_id)
        if person is None:
            raise ConflictError("person not found")
        return person

    def create_person(
        self,
        display_name: str,
        access_level: str = "basic",
        status: str = "active",
        member_id: int | None = None,
        qualifications: Iterable[str] = (),
        guest_valid_from: datetime | None = None,
        guest_valid_until: datetime | None = None,
    ) -> Person:
        require_choice(access_level, ACCESS_LEVELS, "access level")
        require_choice(status, PORTAL_STATUSES, "portal status")
        with self._lock:
            if member_id is not None:
                if member_id not in self.members:
                    raise ConflictError("member not found")
                if self.members[member_id] is not None:
                    raise ConflictError("member already linked")
            person = Person(self._next("person"), display_name, access_level, status)
            self.people[person.id] = person
            if member_id is not None:
                self.members[member_id] = person.id
                self.member_names.setdefault(member_id, display_name)
            for qualification in qualifications:
                self.grant_qualification(
                    person.id,
                    qualification,
                    guest_valid_from if qualification == "guest_player" else None,
                    guest_valid_until if qualification == "guest_player" else None,
                )
            return person

    def add_legacy_member(self, member_id: int, name: str) -> None:
        with self._lock:
            self.members.setdefault(member_id, None)
            self.member_names[member_id] = name

    def create_pending_identity(self, provider: str, subject: str) -> AuthIdentity:
        require_choice(provider, IDENTITY_PROVIDERS, "identity provider")
        with self._lock:
            key = (provider, subject)
            if key in self.identity_keys:
                raise ConflictError("identity already exists")
            identity = AuthIdentity(
                self._next("identity"), provider, subject, "pending", None
            )
            self.identities[identity.id] = identity
            self.identity_keys[key] = identity.id
            return identity

    def identities_for_person(self, person_id: int) -> list[AuthIdentity]:
        return [
            identity
            for identity in self.identities.values()
            if identity.person_id == person_id
        ]

    def qualifications_for_person(self, person_id: int) -> set[str]:
        now = utc_now()
        return {
            qualification
            for (target_id, qualification), row in self.qualifications.items()
            if target_id == person_id
            and is_qualification_active(
                row["status"], row["valid_from"], row["valid_until"], now
            )
        }

    def grant_qualification(
        self,
        person_id: int,
        qualification: str,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> None:
        require_choice(qualification, QUALIFICATIONS, "qualification")
        self.get_person(person_id)
        if qualification == "guest_player":
            validate_guest_period(valid_from, valid_until)
        if valid_from and valid_until and valid_until <= valid_from:
            raise ConflictError("qualification validity is inverted")
        self.qualifications[(person_id, qualification)] = {
            "status": "active",
            "valid_from": valid_from,
            "valid_until": valid_until,
        }

    def approve_identity(
        self,
        actor_id: int,
        identity_id: int,
        reason: str,
        request_id: str,
        person_id: int | None = None,
        display_name: str | None = None,
        member_id: int | None = None,
        qualifications: Iterable[str] = (),
        guest_valid_from: datetime | None = None,
        guest_valid_until: datetime | None = None,
    ) -> Person:
        reason = require_reason(reason)
        with self._lock:
            self._require_admin(actor_id)
            identity = self.identities.get(identity_id)
            if identity is None or identity.status != "pending":
                raise ConflictError("pending identity required")
            if request_id in self.audit_requests:
                raise ConflictError("duplicate request")
            snapshot = copy.deepcopy((self.people, self.members, self.qualifications))
            try:
                if person_id is None:
                    if member_id is not None and member_id not in self.members:
                        raise ConflictError("member not found")
                    if member_id is not None and self.members[member_id] is not None:
                        person_id = self.members[member_id]
                    else:
                        if member_id is not None and not display_name:
                            display_name = self.member_names[member_id]
                        if not display_name:
                            raise ConflictError(
                                "display name required for a new person"
                            )
                        person_id = self.create_person(
                            display_name,
                            member_id=member_id,
                            qualifications=qualifications,
                            guest_valid_from=guest_valid_from,
                            guest_valid_until=guest_valid_until,
                        ).id
                person = self.get_person(person_id)
                linked = AuthIdentity(
                    identity.id,
                    identity.provider,
                    identity.provider_subject,
                    "linked",
                    person.id,
                )
                self.identities[identity.id] = linked
                self.audits.append(
                    {
                        "action": "identity_linked",
                        "actor": actor_id,
                        "target": person.id,
                        "identity": identity_id,
                        "reason": reason,
                        "request_id": request_id,
                    }
                )
                self.audit_requests.add(request_id)
                return person
            except Exception:
                self.people, self.members, self.qualifications = snapshot
                raise

    def block_identity(
        self, actor_id: int, identity_id: int, reason: str, request_id: str
    ) -> AuthIdentity:
        reason = require_reason(reason)
        with self._lock:
            self._require_admin(actor_id)
            identity = self.identities.get(identity_id)
            if identity is None or identity.status != "pending":
                raise ConflictError("pending identity required")
            if request_id in self.audit_requests:
                raise ConflictError("duplicate request")
            blocked = AuthIdentity(
                identity.id,
                identity.provider,
                identity.provider_subject,
                "blocked",
                None,
            )
            self.identities[identity.id] = blocked
            self.audits.append(
                {
                    "action": "identity_blocked",
                    "actor": actor_id,
                    "identity": identity_id,
                    "reason": reason,
                    "request_id": request_id,
                }
            )
            self.audit_requests.add(request_id)
            return blocked

    def change_access(
        self,
        actor_id: int,
        target_id: int,
        access_level: str,
        reason: str,
        request_id: str,
    ) -> Person:
        require_choice(access_level, ACCESS_LEVELS, "access level")
        reason = require_reason(reason)
        with self._lock:
            self._require_admin(actor_id)
            target = self.get_person(target_id)
            if actor_id == target_id and access_level != target.access_level:
                raise AuthorizationError("admins cannot change their own access")
            if request_id in self.audit_requests:
                raise ConflictError("duplicate request")
            if target.is_admin and access_level != "admin":
                active_admins = sum(
                    1 for person in self.people.values() if person.is_admin
                )
                if active_admins <= 1:
                    raise ConflictError("cannot remove the last active admin")
            changed = Person(
                target.id, target.display_name, access_level, target.status
            )
            self.people[target.id] = changed
            self.audits.append(
                {
                    "action": "access_changed",
                    "actor": actor_id,
                    "target": target_id,
                    "before": target.access_level,
                    "after": access_level,
                    "reason": reason,
                    "request_id": request_id,
                }
            )
            self.audit_requests.add(request_id)
            return changed

    def change_status(
        self, actor_id: int, target_id: int, status: str, reason: str, request_id: str
    ) -> Person:
        require_choice(status, PORTAL_STATUSES, "portal status")
        reason = require_reason(reason)
        with self._lock:
            self._require_admin(actor_id)
            target = self.get_person(target_id)
            if actor_id == target_id and status != target.status:
                raise AuthorizationError("admins cannot change their own status")
            if request_id in self.audit_requests:
                raise ConflictError("duplicate request")
            if target.is_admin and status != "active":
                active_admins = sum(
                    1 for person in self.people.values() if person.is_admin
                )
                if active_admins <= 1:
                    raise ConflictError("cannot disable the last active admin")
            changed = Person(
                target.id, target.display_name, target.access_level, status
            )
            self.people[target.id] = changed
            self.audits.append(
                {
                    "action": "status_changed",
                    "actor": actor_id,
                    "target": target_id,
                    "before": target.status,
                    "after": status,
                    "reason": reason,
                    "request_id": request_id,
                }
            )
            self.audit_requests.add(request_id)
            return changed

    def revoke_qualification(self, person_id: int, qualification: str) -> None:
        require_choice(qualification, QUALIFICATIONS, "qualification")
        row = self.qualifications.get((person_id, qualification))
        if row is None:
            raise ConflictError("qualification not found")
        row["status"] = "revoked"

    def create_event(
        self,
        actor_id: int,
        title: str,
        event_type: str,
        start_at: datetime,
        eligibility: Iterable[str],
    ) -> int:
        self._require_event_manager(actor_id)
        rules = {
            require_choice(value, QUALIFICATIONS, "qualification")
            for value in eligibility
        }
        if not rules:
            raise ConflictError("event eligibility cannot be empty")
        event_id = self._next("event")
        self.events[event_id] = {
            "title": title,
            "event_type": event_type,
            "start_at": start_at,
            "status": "draft",
            "eligibility": rules,
        }
        return event_id

    def set_invitee_override(
        self,
        actor_id: int,
        event_id: int,
        person_id: int,
        action: str,
        participation_category: str,
        reason: str,
    ) -> None:
        self._require_event_manager(actor_id)
        self.get_person(person_id)
        if action not in {"include", "exclude"}:
            raise ConflictError("invalid override")
        if participation_category not in QUALIFICATIONS | {"other"}:
            raise ConflictError("invalid participation category")
        if self.events.get(event_id, {}).get("status") != "draft":
            raise ConflictError("only draft events accept overrides")
        self.overrides[(event_id, person_id)] = {
            "action": action,
            "category": participation_category,
            "actor": actor_id,
            "reason": require_reason(reason),
        }

    def publish_event(
        self, actor_id: int, event_id: int, request_id: str
    ) -> list[Invitee]:
        with self._lock:
            self._require_event_manager(actor_id)
            event = self.events.get(event_id)
            if event is None:
                raise ConflictError("event not found")
            if event["status"] == "published":
                return self.event_invitees(event_id)
            if event["status"] != "draft":
                raise ConflictError("draft event required")
            now = utc_now()
            for person in self.people.values():
                if not person.can_use_portal:
                    continue
                matches = (
                    self.qualifications_for_person(person.id) & event["eligibility"]
                )
                if matches:
                    category = next(
                        value
                        for value in (
                            "team_player",
                            "guest_player",
                            "affiliate",
                            "staff",
                        )
                        if value in matches
                    )
                    self.invitees[(event_id, person.id)] = Invitee(
                        event_id, person.id, True, "qualification", category
                    )
            for (override_event_id, person_id), override in self.overrides.items():
                if override_event_id != event_id:
                    continue
                self.invitees[(event_id, person_id)] = Invitee(
                    event_id,
                    person_id,
                    override["action"] == "include",
                    f"manual_{override['action']}",
                    override["category"],
                )
            event["status"] = "published"
            event["published_at"] = now
            return self.event_invitees(event_id)

    def event_invitees(self, event_id: int) -> list[Invitee]:
        return [
            row
            for (target_event_id, _), row in self.invitees.items()
            if target_event_id == event_id
        ]

    def reply_to_event(self, event_id: int, person_id: int, reply: str) -> None:
        require_choice(reply, ATTENDANCE_REPLIES, "attendance reply")
        invitee = self.invitees.get((event_id, person_id))
        if invitee is None or not invitee.included:
            raise AuthorizationError("included invitee required")
        self.replies[(event_id, person_id)] = reply

    def roster_summary(self, event_id: int) -> dict[str, int]:
        result: Counter[str] = Counter()
        for invitee in self.event_invitees(event_id):
            if not invitee.included:
                continue
            reply = self.replies.get((event_id, invitee.person_id), "unanswered")
            result[f"{invitee.participation_category}:{reply}"] += 1
        return dict(result)

    def backfill_members(
        self, fake_admin_member_ids: Iterable[int] = ()
    ) -> BackfillSummary:
        fake_admins = set(fake_admin_member_ids)
        created = linked = qualifications = promoted = 0
        with self._lock:
            for member_id in sorted(self.members):
                person_id = self.members[member_id]
                if person_id is None:
                    person = self.create_person(
                        self.member_names[member_id],
                        access_level="admin" if member_id in fake_admins else "basic",
                        member_id=member_id,
                    )
                    person_id = person.id
                    created += 1
                    linked += 1
                    if member_id in fake_admins:
                        promoted += 1
                elif member_id in fake_admins:
                    person = self.people[person_id]
                    if person.access_level != "admin":
                        self.people[person_id] = Person(
                            person.id, person.display_name, "admin", person.status
                        )
                        promoted += 1
                before = (person_id, "team_player") in self.qualifications
                self.grant_qualification(person_id, "team_player")
                if not before:
                    qualifications += 1
        return BackfillSummary(
            len(self.members), created, linked, qualifications, promoted
        )


class PostgresTeamPortalRepository:
    """PostgreSQL adapter used only when explicitly constructed by local tests."""

    ADMIN_LOCK_KEY = 0x4E545542

    def __init__(self, engine: Engine):
        self.engine = engine

    @staticmethod
    def _person(row: PersonRecord) -> Person:
        return Person(
            row.id, row.display_name, row.portal_access_level, row.portal_status
        )

    @staticmethod
    def _identity(row: AuthIdentityRecord) -> AuthIdentity:
        return AuthIdentity(
            row.id, row.provider, row.provider_subject, row.status, row.person_id
        )

    def _require_admin(
        self, session: Session, person_id: int, for_update: bool = False
    ) -> PersonRecord:
        statement = select(PersonRecord).where(PersonRecord.id == person_id)
        if for_update:
            statement = statement.with_for_update()
        person = session.scalar(statement)
        if (
            person is None
            or person.portal_status != "active"
            or person.portal_access_level != "admin"
        ):
            raise AuthorizationError("active admin required")
        return person

    def _require_event_manager(self, session: Session, person_id: int) -> PersonRecord:
        person = session.scalar(
            select(PersonRecord).where(PersonRecord.id == person_id).with_for_update()
        )
        if (
            person is None
            or person.portal_status != "active"
            or person.portal_access_level not in {"officer", "admin"}
        ):
            raise AuthorizationError("active officer or admin required")
        return person

    def get_person(self, person_id: int) -> Person:
        with Session(self.engine) as session:
            row = session.get(PersonRecord, person_id)
            if row is None:
                raise ConflictError("person not found")
            return self._person(row)

    def create_person(
        self,
        display_name: str,
        access_level: str = "basic",
        status: str = "active",
        member_id: int | None = None,
        qualifications: Iterable[str] = (),
        guest_valid_from: datetime | None = None,
        guest_valid_until: datetime | None = None,
    ) -> Person:
        require_choice(access_level, ACCESS_LEVELS, "access level")
        require_choice(status, PORTAL_STATUSES, "portal status")
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            row = PersonRecord(
                display_name=display_name,
                portal_access_level=access_level,
                portal_status=status,
                version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            if member_id is not None:
                result = session.execute(
                    update(LegacyMemberRecord)
                    .where(
                        LegacyMemberRecord.id == member_id,
                        LegacyMemberRecord.person_id.is_(None),
                    )
                    .values(person_id=row.id)
                )
                if result.rowcount != 1:
                    raise ConflictError("member missing or already linked")
            for qualification in qualifications:
                require_choice(qualification, QUALIFICATIONS, "qualification")
                if qualification == "guest_player":
                    validate_guest_period(guest_valid_from, guest_valid_until)
                session.add(
                    PersonQualificationRecord(
                        person_id=row.id,
                        qualification=qualification,
                        status="active",
                        valid_from=(
                            guest_valid_from
                            if qualification == "guest_player"
                            else None
                        ),
                        valid_until=(
                            guest_valid_until
                            if qualification == "guest_player"
                            else None
                        ),
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.flush()
            return self._person(row)

    def create_pending_identity(self, provider: str, subject: str) -> AuthIdentity:
        require_choice(provider, IDENTITY_PROVIDERS, "identity provider")
        now = utc_now()
        try:
            with Session(self.engine) as session, session.begin():
                row = AuthIdentityRecord(
                    provider=provider,
                    provider_subject=subject,
                    person_id=None,
                    status="pending",
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                session.flush()
                return self._identity(row)
        except IntegrityError as error:
            raise ConflictError("identity already exists") from error

    def identities_for_person(self, person_id: int) -> list[AuthIdentity]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(AuthIdentityRecord).where(
                    AuthIdentityRecord.person_id == person_id
                )
            ).all()
            return [self._identity(row) for row in rows]

    def qualifications_for_person(self, person_id: int) -> set[str]:
        now = utc_now()
        with Session(self.engine) as session:
            return set(
                session.scalars(
                    select(PersonQualificationRecord.qualification).where(
                        PersonQualificationRecord.person_id == person_id,
                        PersonQualificationRecord.status == "active",
                        or_(
                            PersonQualificationRecord.valid_from.is_(None),
                            PersonQualificationRecord.valid_from <= now,
                        ),
                        or_(
                            PersonQualificationRecord.valid_until.is_(None),
                            PersonQualificationRecord.valid_until > now,
                        ),
                    )
                )
            )

    def grant_qualification(
        self,
        person_id: int,
        qualification: str,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> None:
        require_choice(qualification, QUALIFICATIONS, "qualification")
        if qualification == "guest_player":
            validate_guest_period(valid_from, valid_until)
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            row = session.scalar(
                select(PersonQualificationRecord).where(
                    PersonQualificationRecord.person_id == person_id,
                    PersonQualificationRecord.qualification == qualification,
                )
            )
            if row is None:
                session.add(
                    PersonQualificationRecord(
                        person_id=person_id,
                        qualification=qualification,
                        status="active",
                        valid_from=valid_from,
                        valid_until=valid_until,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                row.status = "active"
                row.valid_from = valid_from
                row.valid_until = valid_until
                row.updated_at = now

    def approve_identity(
        self,
        actor_id: int,
        identity_id: int,
        reason: str,
        request_id: str,
        person_id: int | None = None,
        display_name: str | None = None,
        member_id: int | None = None,
        qualifications: Iterable[str] = (),
        guest_valid_from: datetime | None = None,
        guest_valid_until: datetime | None = None,
    ) -> Person:
        reason = require_reason(reason)
        now = utc_now()
        try:
            with Session(self.engine) as session, session.begin():
                self._require_admin(session, actor_id, for_update=True)
                identity = session.scalar(
                    select(AuthIdentityRecord)
                    .where(AuthIdentityRecord.id == identity_id)
                    .with_for_update()
                )
                if identity is None or identity.status != "pending":
                    raise ConflictError("pending identity required")
                if person_id is None and member_id is not None:
                    member = session.scalar(
                        select(LegacyMemberRecord)
                        .where(LegacyMemberRecord.id == member_id)
                        .with_for_update()
                    )
                    if member is None:
                        raise ConflictError("member not found")
                    person_id = member.person_id
                    if person_id is None:
                        if not display_name:
                            display_name = member.name
                        person = PersonRecord(
                            display_name=display_name,
                            portal_access_level="basic",
                            portal_status="active",
                            version=1,
                            created_at=now,
                            updated_at=now,
                        )
                        session.add(person)
                        session.flush()
                        member.person_id = person.id
                        person_id = person.id
                elif person_id is None:
                    if not display_name:
                        raise ConflictError("display name required for a new person")
                    person = PersonRecord(
                        display_name=display_name,
                        portal_access_level="basic",
                        portal_status="active",
                        version=1,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(person)
                    session.flush()
                    person_id = person.id
                person = session.get(PersonRecord, person_id)
                if person is None:
                    raise ConflictError("person not found")
                identity.person_id = person.id
                identity.status = "linked"
                identity.updated_at = now
                for qualification in qualifications:
                    require_choice(qualification, QUALIFICATIONS, "qualification")
                    if qualification == "guest_player":
                        validate_guest_period(guest_valid_from, guest_valid_until)
                    session.add(
                        PersonQualificationRecord(
                            person_id=person.id,
                            qualification=qualification,
                            status="active",
                            valid_from=(
                                guest_valid_from
                                if qualification == "guest_player"
                                else None
                            ),
                            valid_until=(
                                guest_valid_until
                                if qualification == "guest_player"
                                else None
                            ),
                            created_at=now,
                            updated_at=now,
                        )
                    )
                session.add(
                    AccessAuditRecord(
                        action="identity_linked",
                        actor_person_id=actor_id,
                        target_person_id=person.id,
                        auth_identity_id=identity.id,
                        before_state={"identity_status": "pending"},
                        after_state={"identity_status": "linked"},
                        reason=reason,
                        request_id=request_id,
                        created_at=now,
                    )
                )
                session.flush()
                return self._person(person)
        except IntegrityError as error:
            raise ConflictError("identity approval conflict") from error

    def block_identity(
        self, actor_id: int, identity_id: int, reason: str, request_id: str
    ) -> AuthIdentity:
        reason = require_reason(reason)
        now = utc_now()
        try:
            with Session(self.engine) as session, session.begin():
                self._require_admin(session, actor_id, for_update=True)
                identity = session.scalar(
                    select(AuthIdentityRecord)
                    .where(AuthIdentityRecord.id == identity_id)
                    .with_for_update()
                )
                if identity is None or identity.status != "pending":
                    raise ConflictError("pending identity required")
                identity.status = "blocked"
                identity.updated_at = now
                session.add(
                    AccessAuditRecord(
                        action="identity_blocked",
                        actor_person_id=actor_id,
                        target_person_id=None,
                        auth_identity_id=identity.id,
                        before_state={"identity_status": "pending"},
                        after_state={"identity_status": "blocked"},
                        reason=reason,
                        request_id=request_id,
                        created_at=now,
                    )
                )
                session.flush()
                return self._identity(identity)
        except IntegrityError as error:
            raise ConflictError("identity block conflict") from error

    def change_access(
        self,
        actor_id: int,
        target_id: int,
        access_level: str,
        reason: str,
        request_id: str,
    ) -> Person:
        require_choice(access_level, ACCESS_LEVELS, "access level")
        reason = require_reason(reason)
        now = utc_now()
        try:
            with Session(self.engine) as session, session.begin():
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": self.ADMIN_LOCK_KEY},
                )
                self._require_admin(session, actor_id, for_update=True)
                target = session.scalar(
                    select(PersonRecord)
                    .where(PersonRecord.id == target_id)
                    .with_for_update()
                )
                if target is None:
                    raise ConflictError("person not found")
                if actor_id == target_id and access_level != target.portal_access_level:
                    raise AuthorizationError("admins cannot change their own access")
                if target.portal_access_level == "admin" and access_level != "admin":
                    active_admins = session.scalar(
                        select(func.count())
                        .select_from(PersonRecord)
                        .where(
                            PersonRecord.portal_access_level == "admin",
                            PersonRecord.portal_status == "active",
                        )
                    )
                    if active_admins is None or active_admins <= 1:
                        raise ConflictError("cannot remove the last active admin")
                before = target.portal_access_level
                target.portal_access_level = access_level
                target.version += 1
                target.updated_at = now
                session.add(
                    AccessAuditRecord(
                        action="access_changed",
                        actor_person_id=actor_id,
                        target_person_id=target_id,
                        before_state={"access_level": before},
                        after_state={"access_level": access_level},
                        reason=reason,
                        request_id=request_id,
                        created_at=now,
                    )
                )
                session.flush()
                return self._person(target)
        except IntegrityError as error:
            raise ConflictError("access mutation conflict") from error

    def change_status(
        self, actor_id: int, target_id: int, status: str, reason: str, request_id: str
    ) -> Person:
        require_choice(status, PORTAL_STATUSES, "portal status")
        reason = require_reason(reason)
        now = utc_now()
        try:
            with Session(self.engine) as session, session.begin():
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": self.ADMIN_LOCK_KEY},
                )
                self._require_admin(session, actor_id, for_update=True)
                target = session.scalar(
                    select(PersonRecord)
                    .where(PersonRecord.id == target_id)
                    .with_for_update()
                )
                if target is None:
                    raise ConflictError("person not found")
                if actor_id == target_id and status != target.portal_status:
                    raise AuthorizationError("admins cannot change their own status")
                if (
                    target.portal_access_level == "admin"
                    and target.portal_status == "active"
                    and status != "active"
                ):
                    active_admins = session.scalar(
                        select(func.count())
                        .select_from(PersonRecord)
                        .where(
                            PersonRecord.portal_access_level == "admin",
                            PersonRecord.portal_status == "active",
                        )
                    )
                    if active_admins is None or active_admins <= 1:
                        raise ConflictError("cannot disable the last active admin")
                before = target.portal_status
                target.portal_status = status
                target.version += 1
                target.updated_at = now
                session.add(
                    AccessAuditRecord(
                        action="status_changed",
                        actor_person_id=actor_id,
                        target_person_id=target_id,
                        before_state={"status": before},
                        after_state={"status": status},
                        reason=reason,
                        request_id=request_id,
                        created_at=now,
                    )
                )
                session.flush()
                return self._person(target)
        except IntegrityError as error:
            raise ConflictError("status mutation conflict") from error

    def revoke_qualification(self, person_id: int, qualification: str) -> None:
        require_choice(qualification, QUALIFICATIONS, "qualification")
        with Session(self.engine) as session, session.begin():
            row = session.scalar(
                select(PersonQualificationRecord)
                .where(
                    PersonQualificationRecord.person_id == person_id,
                    PersonQualificationRecord.qualification == qualification,
                )
                .with_for_update()
            )
            if row is None:
                raise ConflictError("qualification not found")
            row.status = "revoked"
            row.updated_at = utc_now()

    def create_event(
        self,
        actor_id: int,
        title: str,
        event_type: str,
        start_at: datetime,
        eligibility: Iterable[str],
    ) -> int:
        rules = {
            require_choice(value, QUALIFICATIONS, "qualification")
            for value in eligibility
        }
        if not rules:
            raise ConflictError("event eligibility cannot be empty")
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            self._require_event_manager(session, actor_id)
            event = EventRecord(
                title=title,
                event_type=event_type,
                status="draft",
                start_at=start_at,
                end_at=None,
                created_by_person_id=actor_id,
                published_at=None,
                version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(event)
            session.flush()
            for qualification in rules:
                session.add(
                    EventEligibilityRuleRecord(
                        event_id=event.id, qualification=qualification
                    )
                )
            return event.id

    def set_invitee_override(
        self,
        actor_id: int,
        event_id: int,
        person_id: int,
        action: str,
        participation_category: str,
        reason: str,
    ) -> None:
        if action not in {"include", "exclude"}:
            raise ConflictError("invalid override")
        if participation_category not in QUALIFICATIONS | {"other"}:
            raise ConflictError("invalid participation category")
        reason = require_reason(reason)
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            self._require_event_manager(session, actor_id)
            event = session.get(EventRecord, event_id)
            if event is None or event.status != "draft":
                raise ConflictError("draft event required")
            session.execute(
                insert(EventInviteeOverrideRecord)
                .values(
                    event_id=event_id,
                    person_id=person_id,
                    action=action,
                    participation_category=participation_category,
                    actor_person_id=actor_id,
                    reason=reason,
                    created_at=now,
                )
                .on_conflict_do_update(
                    index_elements=["event_id", "person_id"],
                    set_={
                        "action": action,
                        "participation_category": participation_category,
                        "actor_person_id": actor_id,
                        "reason": reason,
                        "created_at": now,
                    },
                )
            )

    def publish_event(
        self, actor_id: int, event_id: int, request_id: str
    ) -> list[Invitee]:
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            self._require_event_manager(session, actor_id)
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": self.ADMIN_LOCK_KEY + event_id},
            )
            event = session.scalar(
                select(EventRecord).where(EventRecord.id == event_id).with_for_update()
            )
            if event is None:
                raise ConflictError("event not found")
            if event.status == "published":
                return self._event_invitees(session, event_id)
            if event.status != "draft":
                raise ConflictError("draft event required")
            rules = set(
                session.scalars(
                    select(EventEligibilityRuleRecord.qualification).where(
                        EventEligibilityRuleRecord.event_id == event_id
                    )
                )
            )
            qualification_rows = session.execute(
                select(
                    PersonQualificationRecord.person_id,
                    PersonQualificationRecord.qualification,
                )
                .join(
                    PersonRecord, PersonRecord.id == PersonQualificationRecord.person_id
                )
                .where(
                    PersonQualificationRecord.qualification.in_(rules),
                    PersonQualificationRecord.status == "active",
                    PersonRecord.portal_status == "active",
                    PersonRecord.portal_access_level.in_(ACCESS_LEVELS),
                    or_(
                        PersonQualificationRecord.valid_from.is_(None),
                        PersonQualificationRecord.valid_from <= now,
                    ),
                    or_(
                        PersonQualificationRecord.valid_until.is_(None),
                        PersonQualificationRecord.valid_until > now,
                    ),
                )
            ).all()
            candidates: dict[int, str] = {}
            preference = {
                "team_player": 0,
                "guest_player": 1,
                "affiliate": 2,
                "staff": 3,
            }
            for person_id, qualification in qualification_rows:
                current = candidates.get(person_id)
                if current is None or preference[qualification] < preference[current]:
                    candidates[person_id] = qualification
            for person_id, qualification in candidates.items():
                session.add(
                    EventInviteeRecord(
                        event_id=event_id,
                        person_id=person_id,
                        included=True,
                        source="qualification",
                        source_qualification=qualification,
                        participation_category=_category_for(qualification),
                        actor_person_id=None,
                        reason=None,
                        snapshotted_at=now,
                    )
                )
            overrides = session.scalars(
                select(EventInviteeOverrideRecord).where(
                    EventInviteeOverrideRecord.event_id == event_id
                )
            ).all()
            session.flush()
            for override in overrides:
                existing = session.scalar(
                    select(EventInviteeRecord).where(
                        EventInviteeRecord.event_id == event_id,
                        EventInviteeRecord.person_id == override.person_id,
                    )
                )
                values = {
                    "included": override.action == "include",
                    "source": f"manual_{override.action}",
                    "source_qualification": None,
                    "participation_category": override.participation_category,
                    "actor_person_id": override.actor_person_id,
                    "reason": override.reason,
                    "snapshotted_at": now,
                }
                if existing is None:
                    session.add(
                        EventInviteeRecord(
                            event_id=event_id, person_id=override.person_id, **values
                        )
                    )
                else:
                    for field, value in values.items():
                        setattr(existing, field, value)
            event.status = "published"
            event.published_at = now
            event.updated_at = now
            event.version += 1
            session.add(
                EventAuditRecord(
                    event_id=event_id,
                    actor_person_id=actor_id,
                    action="published",
                    reason="publish event invitee snapshot",
                    request_id=request_id,
                    details={"eligibility": sorted(rules)},
                    created_at=now,
                )
            )
            session.flush()
            return self._event_invitees(session, event_id)

    def _event_invitees(self, session: Session, event_id: int) -> list[Invitee]:
        rows = session.scalars(
            select(EventInviteeRecord).where(EventInviteeRecord.event_id == event_id)
        ).all()
        return [
            Invitee(
                row.event_id,
                row.person_id,
                row.included,
                row.source,
                row.participation_category,
            )
            for row in rows
        ]

    def event_invitees(self, event_id: int) -> list[Invitee]:
        with Session(self.engine) as session:
            return self._event_invitees(session, event_id)

    def reply_to_event(self, event_id: int, person_id: int, reply: str) -> None:
        require_choice(reply, ATTENDANCE_REPLIES, "attendance reply")
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            invitee = session.scalar(
                select(EventInviteeRecord).where(
                    EventInviteeRecord.event_id == event_id,
                    EventInviteeRecord.person_id == person_id,
                    EventInviteeRecord.included.is_(True),
                )
            )
            if invitee is None:
                raise AuthorizationError("included invitee required")
            existing = session.scalar(
                select(EventAttendanceReplyRecord).where(
                    EventAttendanceReplyRecord.event_id == event_id,
                    EventAttendanceReplyRecord.person_id == person_id,
                )
            )
            if existing is None:
                session.add(
                    EventAttendanceReplyRecord(
                        event_id=event_id,
                        person_id=person_id,
                        reply=reply,
                        updated_at=now,
                    )
                )
            else:
                existing.reply = reply
                existing.updated_at = now

    def roster_summary(self, event_id: int) -> dict[str, int]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(
                    EventInviteeRecord.participation_category,
                    EventAttendanceReplyRecord.reply,
                )
                .outerjoin(
                    EventAttendanceReplyRecord,
                    and_(
                        EventAttendanceReplyRecord.event_id
                        == EventInviteeRecord.event_id,
                        EventAttendanceReplyRecord.person_id
                        == EventInviteeRecord.person_id,
                    ),
                )
                .where(
                    EventInviteeRecord.event_id == event_id,
                    EventInviteeRecord.included.is_(True),
                )
            ).all()
            result: Counter[str] = Counter()
            for category, reply in rows:
                result[f"{category}:{reply or 'unanswered'}"] += 1
            return dict(result)

    def backfill_members(
        self, fake_admin_member_ids: Iterable[int] = ()
    ) -> BackfillSummary:
        fake_admins = set(fake_admin_member_ids)
        created = linked = qualifications = promoted = 0
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": self.ADMIN_LOCK_KEY}
            )
            members = session.scalars(
                select(LegacyMemberRecord).order_by(LegacyMemberRecord.id)
            ).all()
            for member in members:
                if member.person_id is None:
                    person = PersonRecord(
                        display_name=member.name,
                        portal_access_level=(
                            "admin" if member.id in fake_admins else "basic"
                        ),
                        portal_status="active",
                        version=1,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(person)
                    session.flush()
                    member.person_id = person.id
                    created += 1
                    linked += 1
                    if member.id in fake_admins:
                        promoted += 1
                else:
                    person = session.get(PersonRecord, member.person_id)
                    if person is None:
                        raise ConflictError("member points to a missing person")
                    if (
                        member.id in fake_admins
                        and person.portal_access_level != "admin"
                    ):
                        person.portal_access_level = "admin"
                        person.updated_at = now
                        person.version += 1
                        promoted += 1
                existing = session.scalar(
                    select(PersonQualificationRecord).where(
                        PersonQualificationRecord.person_id == member.person_id,
                        PersonQualificationRecord.qualification == "team_player",
                    )
                )
                if existing is None:
                    session.add(
                        PersonQualificationRecord(
                            person_id=member.person_id,
                            qualification="team_player",
                            status="active",
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    qualifications += 1
                session.execute(
                    insert(AccessAuditRecord)
                    .values(
                        action="member_backfilled",
                        actor_person_id=None,
                        target_person_id=member.person_id,
                        auth_identity_id=None,
                        before_state=None,
                        after_state={"member_id": member.id},
                        reason="local legacy member backfill rehearsal",
                        request_id=f"backfill-member-{member.id}",
                        created_at=now,
                    )
                    .on_conflict_do_nothing(index_elements=["request_id"])
                )
        return BackfillSummary(len(members), created, linked, qualifications, promoted)
