from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import Engine, func, or_, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .domain import (
    AuthIdentity,
    AuthorizationError,
    ConflictError,
    Person,
    Principal,
    ReviewMessage,
    ValidationError,
    is_qualification_active,
    require_choice,
    require_reason,
    validate_guest_period,
)
from .models import (
    AccessAuditRecord,
    AuthIdentityRecord,
    IdentityReviewMessageRecord,
    IdentityReviewThreadRecord,
    LegacyGameAttendanceReplyRecord,
    LegacyGameRecord,
    LegacyLineUserRecord,
    LegacyMemberRecord,
    PersonQualificationRecord,
    PersonRecord,
)

IDENTITY_STATUSES = frozenset({"pending", "linked", "disabled", "blocked"})
PERSON_TRANSITIONS = {
    "active": frozenset({"disabled", "blocked"}),
    "disabled": frozenset({"active"}),
    "blocked": frozenset({"active"}),
    "inactive": frozenset({"active"}),
}
QUALIFICATIONS = frozenset({"team_player", "guest_player", "affiliate", "staff"})
APPLICANT_MESSAGE_INTERVAL = timedelta(hours=24)
REVIEW_RETENTION = timedelta(days=365)
ADMIN_LOCK_KEY = 70070
BOOTSTRAP_REASON_PREFIX = "Zero-admin bootstrap: "


@dataclass(frozen=True)
class PendingIdentityResult:
    identity: AuthIdentity
    created: bool


@dataclass(frozen=True)
class AttendanceSummary:
    participants: tuple[dict, ...]
    team_player_total: int
    team_player_replied: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_name(value: str, field: str = "display name") -> str:
    cleaned = value.strip()
    if not 1 <= len(cleaned) <= 120:
        raise ValidationError(f"{field} must contain 1 to 120 characters")
    return cleaned


def _clean_note(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > 1000:
        raise ValidationError("admin note cannot exceed 1000 characters")
    return cleaned


class IdentityLifecycleRepository:
    """Transactional Phase C bridge for portal and legacy identity data."""

    def __init__(
        self,
        engine: Engine,
        admin_member_ids: Iterable[int] = (),
        *,
        allow_persisted_admins: bool = False,
    ):
        self.engine = engine
        self.admin_member_ids = frozenset(int(value) for value in admin_member_ids)
        self.allow_persisted_admins = allow_persisted_admins is True

    @staticmethod
    def _identity(row: AuthIdentityRecord) -> AuthIdentity:
        return AuthIdentity(
            row.id, row.provider, row.provider_subject, row.status, row.person_id
        )

    @staticmethod
    def _person(row: PersonRecord, member: LegacyMemberRecord | None = None) -> Person:
        return Person(
            row.id,
            row.display_name,
            row.portal_access_level,
            row.portal_status,
            member.name if member is not None else row.formal_name,
            member.id if member is not None else None,
        )

    @staticmethod
    def _audit_exists(session: Session, request_id: str) -> bool:
        return (
            session.scalar(
                select(AccessAuditRecord.id).where(
                    AccessAuditRecord.request_id == request_id
                )
            )
            is not None
        )

    @staticmethod
    def _thread(
        session: Session, identity_id: int, now: datetime
    ) -> IdentityReviewThreadRecord:
        thread = session.scalar(
            select(IdentityReviewThreadRecord)
            .where(IdentityReviewThreadRecord.auth_identity_id == identity_id)
            .with_for_update()
        )
        if thread is None:
            thread = IdentityReviewThreadRecord(
                auth_identity_id=identity_id,
                status="open",
                last_applicant_message_at=None,
                last_activity_at=now,
                closed_at=None,
                redacted_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(thread)
            session.flush()
        return thread

    def _require_admin(
        self, session: Session, actor_person_id: int
    ) -> LegacyMemberRecord:
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADMIN_LOCK_KEY}
        )
        person = session.scalar(
            select(PersonRecord)
            .where(PersonRecord.id == actor_person_id)
            .with_for_update()
        )
        member = session.scalar(
            select(LegacyMemberRecord).where(
                LegacyMemberRecord.person_id == actor_person_id,
            )
        )
        linked = session.scalar(
            select(func.count(AuthIdentityRecord.id)).where(
                AuthIdentityRecord.person_id == actor_person_id,
                AuthIdentityRecord.status == "linked",
            )
        )
        if (
            person is None
            or person.portal_status != "active"
            or member is None
            or (
                member.id not in self.admin_member_ids
                and not (
                    self.allow_persisted_admins
                    and person.portal_access_level == "admin"
                )
            )
            or not linked
        ):
            raise AuthorizationError("active allowlisted administrator required")
        return member

    def ensure_pending_line_identity(
        self, subject: str, nickname: str, request_id: str
    ) -> PendingIdentityResult:
        subject = subject.strip()
        nickname = _clean_name(nickname, "LINE display name")
        if not subject or len(subject) > 255:
            raise ValidationError("invalid LINE subject")
        now = utc_now()
        try:
            with Session(self.engine) as session, session.begin():
                identity = session.scalar(
                    select(AuthIdentityRecord)
                    .where(
                        AuthIdentityRecord.provider == "line",
                        AuthIdentityRecord.provider_subject == subject,
                    )
                    .with_for_update()
                )
                if identity is not None:
                    return PendingIdentityResult(self._identity(identity), False)
                legacy = session.scalar(
                    select(LegacyLineUserRecord)
                    .where(LegacyLineUserRecord.line_user_id == subject)
                    .with_for_update()
                )
                if legacy is None:
                    legacy = LegacyLineUserRecord(
                        nickname=nickname,
                        line_user_id=subject,
                        member_id=None,
                        submit_time=now,
                        has_replied=False,
                        ignored=False,
                    )
                    session.add(legacy)
                identity = AuthIdentityRecord(
                    provider="line",
                    provider_subject=subject,
                    person_id=None,
                    status="pending",
                    created_at=now,
                    updated_at=now,
                )
                session.add(identity)
                session.flush()
                self._thread(session, identity.id, now)
                session.add(
                    AccessAuditRecord(
                        action="identity_pending",
                        actor_person_id=None,
                        target_person_id=None,
                        auth_identity_id=identity.id,
                        before_state=None,
                        after_state={"status": "pending"},
                        reason="LINE identity awaiting administrator review",
                        request_id=request_id,
                        created_at=now,
                    )
                )
                session.flush()
                return PendingIdentityResult(self._identity(identity), True)
        except IntegrityError as error:
            raise ConflictError("identity creation conflict") from error

    def resolve_line_principal(
        self, subject: str, at: datetime | None = None
    ) -> Principal | None:
        at = at or utc_now()
        with Session(self.engine) as session:
            row = session.scalar(
                select(AuthIdentityRecord).where(
                    AuthIdentityRecord.provider == "line",
                    AuthIdentityRecord.provider_subject == subject,
                )
            )
            if row is None or row.status != "linked" or row.person_id is None:
                return None
            person = session.get(PersonRecord, row.person_id)
            if person is None or person.portal_status != "active":
                return None
            member = session.scalar(
                select(LegacyMemberRecord).where(
                    LegacyMemberRecord.person_id == person.id
                )
            )
            qualifications = session.scalars(
                select(PersonQualificationRecord).where(
                    PersonQualificationRecord.person_id == person.id,
                    PersonQualificationRecord.status == "active",
                    or_(
                        PersonQualificationRecord.valid_from.is_(None),
                        PersonQualificationRecord.valid_from <= at,
                    ),
                    or_(
                        PersonQualificationRecord.valid_until.is_(None),
                        PersonQualificationRecord.valid_until > at,
                    ),
                )
            ).all()
            return Principal(
                self._person(person, member),
                self._identity(row),
                frozenset(item.qualification for item in qualifications),
            )

    def local_preview_identities(self) -> tuple[dict, ...]:
        """Return a safe chooser projection without provider subjects."""
        with Session(self.engine) as session:
            rows = session.execute(
                select(AuthIdentityRecord, PersonRecord, LegacyMemberRecord)
                .join(PersonRecord, PersonRecord.id == AuthIdentityRecord.person_id)
                .outerjoin(
                    LegacyMemberRecord,
                    LegacyMemberRecord.person_id == PersonRecord.id,
                )
                .where(
                    AuthIdentityRecord.provider == "line",
                    AuthIdentityRecord.status == "linked",
                    PersonRecord.portal_status == "active",
                )
                .order_by(PersonRecord.id)
                .limit(100)
            ).all()
            return tuple(
                {
                    "identity_id": identity.id,
                    "person_id": person.id,
                    "display_name": person.display_name,
                    "formal_name": person.formal_name,
                    "access_level": person.portal_access_level,
                    "member_id": member.id if member is not None else None,
                }
                for identity, person, member in rows
            )

    def local_preview_principal(self, identity_id: int) -> Principal | None:
        """Resolve one imported pseudonymous identity for localhost login."""
        with Session(self.engine) as session:
            subject = session.scalar(
                select(AuthIdentityRecord.provider_subject).where(
                    AuthIdentityRecord.id == identity_id,
                    AuthIdentityRecord.provider == "line",
                    AuthIdentityRecord.status == "linked",
                )
            )
        return self.resolve_line_principal(subject) if subject is not None else None

    def is_fictional_demo_fixture(self) -> bool:
        """Recognize only the complete TASK-099 reserved fictional fixture."""
        with Session(self.engine) as session:
            counts = {
                "people": (PersonRecord, 18),
                "members": (LegacyMemberRecord, 17),
                "auth_identities": (AuthIdentityRecord, 3),
                "person_qualifications": (PersonQualificationRecord, 17),
                "games": (LegacyGameRecord, 4),
                "line_users": (LegacyLineUserRecord, 15),
                "game_attendance_replies": (LegacyGameAttendanceReplyRecord, 12),
            }
            if any(
                session.scalar(select(func.count()).select_from(model)) != expected
                for model, expected in counts.values()
            ):
                return False
            marker = session.scalar(
                select(func.count(AccessAuditRecord.id)).where(
                    AccessAuditRecord.request_id == "task099-demo-seed"
                )
            )
            subjects = session.scalars(
                select(AuthIdentityRecord.provider_subject)
            ).all()
            exact_shape = session.scalar(
                text(
                    """
                    SELECT
                      NOT EXISTS (SELECT 1 FROM ntubtob.people WHERE id NOT BETWEEN 7101 AND 7118)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.members WHERE id NOT BETWEEN 7101 AND 7117)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.games WHERE id NOT BETWEEN 9710 AND 9713)
                      AND NOT EXISTS (
                        SELECT 1 FROM ntubtob.person_qualifications
                        WHERE person_id NOT BETWEEN 7101 AND 7118
                      )
                      AND NOT EXISTS (
                        SELECT 1 FROM ntubtob.line_users
                        WHERE line_user_id NOT LIKE 'task099-fictional-line-%'
                      )
                      AND NOT EXISTS (
                        SELECT 1 FROM ntubtob.game_attendance_replies
                        WHERE game_id NOT BETWEEN 9710 AND 9713
                           OR person_id NOT BETWEEN 7101 AND 7118
                      )
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.identity_review_threads)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.identity_review_messages)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.ballparks)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.cancellations)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.discord_webhooks)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.line_groups)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.line_notify_tokens)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.events)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.activities)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.event_eligibility_rules)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.event_invitee_overrides)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.event_invitees)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.event_attendance_replies)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.activity_attendance_replies)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.event_managers)
                      AND NOT EXISTS (SELECT 1 FROM ntubtob.event_audit)
                      AND NOT EXISTS (
                        SELECT 1 FROM ntubtob.access_audit
                        WHERE
                          (request_id = 'task099-demo-seed' AND NOT (
                            action = 'access_changed' AND actor_person_id = 7101
                            AND target_person_id = 7102 AND auth_identity_id IS NULL
                            AND before_state::jsonb = '{"access_level":"officer"}'::jsonb
                            AND after_state::jsonb = '{"access_level":"officer","fixture":"TASK-099"}'::jsonb
                            AND reason = 'TASK-099 fictional fixture'
                          ))
                          OR
                          (request_id <> 'task099-demo-seed' AND NOT (
                            action = 'access_changed' AND actor_person_id = 7101
                            AND target_person_id BETWEEN 7102 AND 7118
                            AND auth_identity_id IS NULL
                            AND reason = 'TASK-099 fictional access rehearsal'
                            AND request_id = 'person-access-' || target_person_id::text
                              || '-' || ((after_state::jsonb)->>'access_level')
                            AND (
                              (target_person_id = 7102
                               AND before_state::jsonb = '{"access_level":"officer"}'::jsonb
                               AND after_state::jsonb = '{"access_level":"basic"}'::jsonb)
                              OR
                              (target_person_id BETWEEN 7103 AND 7118
                               AND before_state::jsonb = '{"access_level":"basic"}'::jsonb
                               AND after_state::jsonb = '{"access_level":"officer"}'::jsonb)
                            )
                          ))
                      )
                      AND NOT EXISTS (
                        SELECT target_person_id FROM ntubtob.access_audit
                        WHERE request_id <> 'task099-demo-seed'
                        GROUP BY target_person_id HAVING count(*) <> 1
                      )
                      AND NOT EXISTS (
                        SELECT 1 FROM ntubtob.people p
                        WHERE p.id BETWEEN 7101 AND 7118 AND (
                          (p.id = 7101 AND
                           (p.portal_access_level <> 'admin' OR p.version <> 1))
                          OR (p.id = 7102 AND (
                            p.portal_access_level <> CASE WHEN EXISTS (
                              SELECT 1 FROM ntubtob.access_audit a
                              WHERE a.target_person_id = p.id
                                AND a.request_id <> 'task099-demo-seed'
                            ) THEN 'basic' ELSE 'officer' END
                            OR p.version <> 1 + (SELECT count(*)
                              FROM ntubtob.access_audit a
                              WHERE a.target_person_id = p.id
                                AND a.request_id <> 'task099-demo-seed')
                          ))
                          OR (p.id BETWEEN 7103 AND 7118 AND (
                            p.portal_access_level <> CASE WHEN EXISTS (
                              SELECT 1 FROM ntubtob.access_audit a
                              WHERE a.target_person_id = p.id
                                AND a.request_id <> 'task099-demo-seed'
                            ) THEN 'officer' ELSE 'basic' END
                            OR p.version <> 1 + (SELECT count(*)
                              FROM ntubtob.access_audit a
                              WHERE a.target_person_id = p.id
                                AND a.request_id <> 'task099-demo-seed')
                          ))
                        )
                      )
                      AND (SELECT count(*) FROM ntubtob.attendance_reply_types) = 5
                    """
                )
            )
            return (
                marker == 1
                and exact_shape is True
                and all(
                    isinstance(subject, str)
                    and subject.startswith("task099-fictional-")
                    for subject in subjects
                )
            )

    def identity_status(self, subject: str) -> str | None:
        with Session(self.engine) as session:
            return session.scalar(
                select(AuthIdentityRecord.status).where(
                    AuthIdentityRecord.provider == "line",
                    AuthIdentityRecord.provider_subject == subject,
                )
            )

    def identity_status_for_id(self, identity_id: int) -> str | None:
        with Session(self.engine) as session:
            return session.scalar(
                select(AuthIdentityRecord.status).where(
                    AuthIdentityRecord.id == identity_id
                )
            )

    def line_identity(self, subject: str) -> AuthIdentity | None:
        with Session(self.engine) as session:
            row = session.scalar(
                select(AuthIdentityRecord).where(
                    AuthIdentityRecord.provider == "line",
                    AuthIdentityRecord.provider_subject == subject,
                )
            )
            return self._identity(row) if row is not None else None

    def admin_dashboard(self, actor_person_id: int) -> dict[str, tuple[dict, ...]]:
        """Return a bounded overview without provider subjects or raw audit JSON."""
        with Session(self.engine) as session:
            self._require_admin(session, actor_person_id)
            qualification_rows = session.scalars(
                select(PersonQualificationRecord).order_by(
                    PersonQualificationRecord.person_id,
                    PersonQualificationRecord.qualification,
                )
            ).all()
            by_person: dict[int, list[dict]] = {}
            for qualification in qualification_rows:
                by_person.setdefault(qualification.person_id, []).append(
                    {
                        "name": qualification.qualification,
                        "status": qualification.status,
                        "valid_from": qualification.valid_from,
                        "valid_until": qualification.valid_until,
                    }
                )
            identity_rows = session.execute(
                select(
                    AuthIdentityRecord,
                    PersonRecord,
                    LegacyMemberRecord,
                    LegacyLineUserRecord,
                    IdentityReviewThreadRecord,
                )
                .outerjoin(
                    PersonRecord, PersonRecord.id == AuthIdentityRecord.person_id
                )
                .outerjoin(
                    LegacyMemberRecord, LegacyMemberRecord.person_id == PersonRecord.id
                )
                .outerjoin(
                    LegacyLineUserRecord,
                    LegacyLineUserRecord.line_user_id
                    == AuthIdentityRecord.provider_subject,
                )
                .outerjoin(
                    IdentityReviewThreadRecord,
                    IdentityReviewThreadRecord.auth_identity_id
                    == AuthIdentityRecord.id,
                )
                .where(AuthIdentityRecord.provider == "line")
                .order_by(AuthIdentityRecord.created_at.desc())
                .limit(250)
            ).all()
            identities = []
            now = utc_now()
            for identity, person, member, legacy, thread in identity_rows:
                formal = (
                    member.name if member else (person.formal_name if person else None)
                )
                identities.append(
                    {
                        "identity_id": identity.id,
                        "nickname": legacy.nickname if legacy else "LINE applicant",
                        "identity_status": identity.status,
                        "ignored": legacy.ignored if legacy else False,
                        "person_id": person.id if person else None,
                        "person_name": (
                            (formal or person.display_name) if person else None
                        ),
                        "person_status": person.portal_status if person else None,
                        "member_id": member.id if member else None,
                        "qualifications": (
                            tuple(by_person.get(person.id, ())) if person else ()
                        ),
                        "review_status": thread.status if thread else None,
                        "last_activity_at": (
                            thread.last_activity_at if thread else identity.updated_at
                        ),
                        "stale": now
                        - (thread.last_activity_at if thread else identity.updated_at)
                        >= timedelta(days=30),
                    }
                )
            people = tuple(
                {
                    "person_id": person.id,
                    "display_name": person.display_name,
                    "formal_name": person.formal_name,
                    "admin_note": person.admin_note,
                    "status": person.portal_status,
                    "access_level": person.portal_access_level,
                    "member_id": member.id if member else None,
                    "qualifications": tuple(by_person.get(person.id, ())),
                }
                for person, member in session.execute(
                    select(PersonRecord, LegacyMemberRecord)
                    .outerjoin(
                        LegacyMemberRecord,
                        LegacyMemberRecord.person_id == PersonRecord.id,
                    )
                    .order_by(PersonRecord.id)
                    .limit(500)
                )
            )
            audit = tuple(
                {
                    "action": row.action,
                    "actor_person_id": row.actor_person_id,
                    "target_person_id": row.target_person_id,
                    "auth_identity_id": row.auth_identity_id,
                    "reason": row.reason,
                    "created_at": row.created_at,
                }
                for row in session.scalars(
                    select(AccessAuditRecord)
                    .order_by(
                        AccessAuditRecord.created_at.desc(),
                        AccessAuditRecord.id.desc(),
                    )
                    .limit(100)
                )
            )
            available_members = tuple(
                {"member_id": member.id, "name": member.name}
                for member in session.scalars(
                    select(LegacyMemberRecord)
                    .where(LegacyMemberRecord.person_id.is_(None))
                    .order_by(LegacyMemberRecord.id)
                    .limit(250)
                )
            )
            return {
                "identities": tuple(identities),
                "people": people,
                "available_members": available_members,
                "audit": audit,
            }

    def change_access(
        self,
        actor_person_id: int,
        target_person_id: int,
        access_level: str,
        reason: str,
        request_id: str,
    ) -> Person:
        """Apply only the audited basic/officer transition used by Portal admin."""
        if access_level not in {"basic", "officer"}:
            raise ValidationError("access level must be basic or officer")
        reason = require_reason(reason)
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            self._require_admin(session, actor_person_id)
            target = session.scalar(
                select(PersonRecord)
                .where(PersonRecord.id == target_person_id)
                .with_for_update()
            )
            if target is None:
                raise ConflictError("person not found")
            if actor_person_id == target_person_id:
                raise AuthorizationError(
                    "administrators cannot change their own access"
                )
            transition = (target.portal_access_level, access_level)
            if transition not in {("basic", "officer"), ("officer", "basic")}:
                raise ConflictError("only basic and officer may be exchanged")
            if access_level == "officer" and target.portal_status != "active":
                raise ConflictError("only active people may become officers")
            if self._audit_exists(session, request_id):
                raise ConflictError("request already applied")
            before = target.portal_access_level
            target.portal_access_level = access_level
            target.version += 1
            target.updated_at = now
            session.add(
                AccessAuditRecord(
                    action="access_changed",
                    actor_person_id=actor_person_id,
                    target_person_id=target_person_id,
                    auth_identity_id=None,
                    before_state={"access_level": before},
                    after_state={"access_level": access_level},
                    reason=reason,
                    request_id=request_id,
                    created_at=now,
                )
            )
            member = session.scalar(
                select(LegacyMemberRecord).where(
                    LegacyMemberRecord.person_id == target_person_id
                )
            )
            session.flush()
            return self._person(target, member)

    def person_directory(self, actor_person_id: int) -> tuple[dict, ...]:
        """Return only the low-sensitivity Person directory projection."""
        with Session(self.engine) as session:
            person = session.scalar(
                select(PersonRecord).where(
                    PersonRecord.id == actor_person_id,
                    PersonRecord.portal_status == "active",
                )
            )
            if person is None:
                raise AuthorizationError("active person required")
            rows = session.execute(
                select(
                    PersonRecord.id,
                    PersonRecord.display_name,
                    PersonRecord.formal_name,
                    PersonRecord.portal_access_level,
                    PersonRecord.portal_status,
                    LegacyMemberRecord.id,
                )
                .outerjoin(
                    LegacyMemberRecord,
                    LegacyMemberRecord.person_id == PersonRecord.id,
                )
                .order_by(PersonRecord.id)
                .limit(500)
            ).all()
            qualifications = session.execute(
                select(
                    PersonQualificationRecord.person_id,
                    PersonQualificationRecord.qualification,
                    PersonQualificationRecord.status,
                ).order_by(
                    PersonQualificationRecord.person_id,
                    PersonQualificationRecord.qualification,
                )
            ).all()
            by_person: dict[int, list[dict]] = {}
            for person_id, qualification, status in qualifications:
                by_person.setdefault(person_id, []).append(
                    {"name": qualification, "status": status}
                )
            return tuple(
                {
                    "person_id": person_id,
                    "display_name": display_name,
                    "formal_name": formal_name,
                    "portal_access_level": access_level,
                    "portal_status": status,
                    "status": status,
                    "member_id": member_id,
                    "qualifications": tuple(by_person.get(person_id, ())),
                }
                for (
                    person_id,
                    display_name,
                    formal_name,
                    access_level,
                    status,
                    member_id,
                ) in rows
            )

    def create_member_person(
        self,
        actor_person_id: int,
        member_id: int,
        display_name: str,
        reason: str,
        request_id: str,
        qualifications: Iterable[str] = (),
    ) -> Person:
        """Create the Person link for an existing unlinked Member atomically."""
        display_name = _clean_name(display_name)
        reason = require_reason(reason)
        requested = frozenset(qualifications)
        if not requested <= QUALIFICATIONS:
            raise ValidationError("unknown qualification")
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            self._require_admin(session, actor_person_id)
            if self._audit_exists(session, request_id):
                raise ConflictError("request already applied")
            member = session.scalar(
                select(LegacyMemberRecord)
                .where(LegacyMemberRecord.id == member_id)
                .with_for_update()
            )
            if member is None or member.person_id is not None:
                raise ConflictError("unlinked Member required")
            person = PersonRecord(
                display_name=display_name,
                formal_name=member.name,
                admin_note=None,
                portal_access_level="basic",
                portal_status="active",
                version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(person)
            session.flush()
            member.person_id = person.id
            for qualification in sorted(requested | {"team_player"}):
                session.add(
                    PersonQualificationRecord(
                        person_id=person.id,
                        qualification=qualification,
                        status="active",
                        valid_from=None,
                        valid_until=None,
                        granted_by_person_id=actor_person_id,
                        reason=reason,
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.add(
                AccessAuditRecord(
                    action="member_person_created",
                    actor_person_id=actor_person_id,
                    target_person_id=person.id,
                    auth_identity_id=None,
                    before_state={"member_id": member.id, "person_id": None},
                    after_state={"member_id": member.id, "person_id": person.id},
                    reason=reason,
                    request_id=request_id,
                    created_at=now,
                )
            )
            return self._person(person, member)

    def approve_member(
        self,
        actor_person_id: int,
        identity_id: int,
        member_id: int,
        reason: str,
        request_id: str,
    ) -> Principal:
        reason = require_reason(reason)
        now = utc_now()
        try:
            with Session(self.engine) as session, session.begin():
                self._require_admin(session, actor_person_id)
                subject = self._approve_member_in_transaction(
                    session,
                    identity_id,
                    member_id,
                    reason,
                    request_id,
                    now,
                    actor_person_id,
                )
            principal = self.resolve_line_principal(subject, now)
            if principal is None:
                raise ConflictError("approved principal did not resolve")
            return principal
        except IntegrityError as error:
            raise ConflictError("identity approval conflict") from error

    def _approve_member_in_transaction(
        self,
        session: Session,
        identity_id: int,
        member_id: int,
        reason: str,
        request_id: str,
        now: datetime,
        actor_person_id: int | None,
        *,
        strict_bootstrap: bool = False,
    ) -> str:
        """Apply the shared Member-linking invariants inside an open transaction."""
        if self._audit_exists(session, request_id):
            identity = session.get(AuthIdentityRecord, identity_id)
            audit = session.scalar(
                select(AccessAuditRecord).where(
                    AccessAuditRecord.request_id == request_id
                )
            )
            if (
                identity is None
                or identity.status != "linked"
                or audit is None
                or audit.action != "identity_linked"
                or audit.auth_identity_id != identity_id
                or (audit.after_state or {}).get("member_id") != member_id
                or audit.after_state != {"status": "linked", "member_id": member_id}
                or (
                    strict_bootstrap
                    and (
                        audit.actor_person_id is not None
                        or audit.target_person_id != identity.person_id
                        or audit.before_state != {"status": "pending"}
                        or audit.reason != reason
                    )
                )
            ):
                raise ConflictError("idempotent approval state drift")
            return identity.provider_subject
        identity = session.scalar(
            select(AuthIdentityRecord)
            .where(AuthIdentityRecord.id == identity_id)
            .with_for_update()
        )
        member = session.scalar(
            select(LegacyMemberRecord)
            .where(LegacyMemberRecord.id == member_id)
            .with_for_update()
        )
        if identity is None or identity.provider != "line":
            raise ConflictError("LINE identity not found")
        if identity.status != "pending" or identity.person_id is not None:
            raise ConflictError("pending identity required")
        if member is None or member.person_id is None:
            raise ConflictError("Member with Person link required")
        person = session.scalar(
            select(PersonRecord)
            .where(PersonRecord.id == member.person_id)
            .with_for_update()
        )
        if person is None or person.portal_status in {"disabled", "blocked"}:
            raise ConflictError("eligible target Person required")
        legacy = session.scalar(
            select(LegacyLineUserRecord)
            .where(LegacyLineUserRecord.line_user_id == identity.provider_subject)
            .with_for_update()
        )
        if legacy is None or legacy.member_id is not None:
            raise ConflictError("unlinked legacy identity required")
        if strict_bootstrap and legacy.ignored:
            raise ConflictError("unignored legacy identity required")
        person.portal_status = "active"
        person.version += 1
        person.updated_at = now
        identity.person_id = person.id
        identity.status = "linked"
        identity.updated_at = now
        legacy.member_id = member.id
        legacy.ignored = False
        qualification = session.scalar(
            select(PersonQualificationRecord)
            .where(
                PersonQualificationRecord.person_id == person.id,
                PersonQualificationRecord.qualification == "team_player",
            )
            .with_for_update()
        )
        if qualification is None:
            session.add(
                PersonQualificationRecord(
                    person_id=person.id,
                    qualification="team_player",
                    status="active",
                    valid_from=None,
                    valid_until=None,
                    granted_by_person_id=actor_person_id,
                    reason=reason,
                    created_at=now,
                    updated_at=now,
                )
            )
        elif strict_bootstrap and qualification.status != "active":
            raise ConflictError("active team player qualification required")
        thread = self._thread(session, identity.id, now)
        if strict_bootstrap and (
            thread.status != "open"
            or thread.closed_at is not None
            or thread.redacted_at
        ):
            raise ConflictError("open review thread required")
        thread.status = "closed"
        thread.closed_at = now
        thread.last_activity_at = now
        thread.updated_at = now
        session.add(
            AccessAuditRecord(
                action="identity_linked",
                actor_person_id=actor_person_id,
                target_person_id=person.id,
                auth_identity_id=identity.id,
                before_state={"status": "pending"},
                after_state={"status": "linked", "member_id": member.id},
                reason=reason,
                request_id=request_id,
                created_at=now,
            )
        )
        return identity.provider_subject

    def bootstrap_zero_admin_member(
        self, identity_id: int, member_id: int, reason: str, request_id: str
    ) -> Principal:
        """Link the one allowlisted bootstrap principal when no admin exists."""
        reason = require_reason(reason)
        reason = require_reason(f"{BOOTSTRAP_REASON_PREFIX}{reason}")
        now = utc_now()
        try:
            with Session(self.engine) as session, session.begin():
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": ADMIN_LOCK_KEY},
                )
                if self._audit_exists(session, request_id):
                    subject = self._approve_member_in_transaction(
                        session,
                        identity_id,
                        member_id,
                        reason,
                        request_id,
                        now,
                        None,
                        strict_bootstrap=True,
                    )
                else:
                    if member_id not in self.admin_member_ids:
                        raise AuthorizationError(
                            "allowlisted bootstrap Member required"
                        )
                    active_admins = session.scalar(
                        select(func.count(func.distinct(PersonRecord.id)))
                        .select_from(PersonRecord)
                        .join(
                            LegacyMemberRecord,
                            LegacyMemberRecord.person_id == PersonRecord.id,
                        )
                        .join(
                            AuthIdentityRecord,
                            AuthIdentityRecord.person_id == PersonRecord.id,
                        )
                        .where(
                            PersonRecord.portal_status == "active",
                            LegacyMemberRecord.id.in_(self.admin_member_ids or {-1}),
                            AuthIdentityRecord.status == "linked",
                        )
                    )
                    if active_admins != 0:
                        raise ConflictError(
                            "active allowlisted administrator already exists"
                        )
                    subject = self._approve_member_in_transaction(
                        session,
                        identity_id,
                        member_id,
                        reason,
                        request_id,
                        now,
                        None,
                        strict_bootstrap=True,
                    )
            principal = self.resolve_line_principal(subject, now)
            if principal is None:
                raise ConflictError("bootstrap principal did not resolve")
            return principal
        except SQLAlchemyError as error:
            raise ConflictError("zero-admin bootstrap conflict") from error

    def approve_non_member(
        self,
        actor_person_id: int,
        identity_id: int,
        display_name: str,
        reason: str,
        request_id: str,
        formal_name: str | None = None,
        qualifications: Iterable[str] = (),
        guest_valid_from: datetime | None = None,
        guest_valid_until: datetime | None = None,
    ) -> Principal:
        display_name = _clean_name(display_name)
        formal_name = _clean_name(formal_name, "formal name") if formal_name else None
        reason = require_reason(reason)
        requested = frozenset(qualifications)
        if not requested <= QUALIFICATIONS - {"team_player"}:
            raise ValidationError("non-Member cannot receive team_player")
        if "guest_player" in requested:
            validate_guest_period(guest_valid_from, guest_valid_until)
        now = utc_now()
        try:
            with Session(self.engine) as session, session.begin():
                self._require_admin(session, actor_person_id)
                identity = session.scalar(
                    select(AuthIdentityRecord)
                    .where(AuthIdentityRecord.id == identity_id)
                    .with_for_update()
                )
                if (
                    identity is None
                    or identity.status != "pending"
                    or identity.person_id
                ):
                    raise ConflictError("pending identity required")
                if self._audit_exists(session, request_id):
                    raise ConflictError("request already applied")
                person = PersonRecord(
                    display_name=display_name,
                    formal_name=formal_name,
                    admin_note=None,
                    portal_access_level="basic",
                    portal_status="active",
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(person)
                session.flush()
                identity.person_id = person.id
                identity.status = "linked"
                identity.updated_at = now
                legacy = session.scalar(
                    select(LegacyLineUserRecord)
                    .where(
                        LegacyLineUserRecord.line_user_id == identity.provider_subject
                    )
                    .with_for_update()
                )
                if legacy is None:
                    raise ConflictError("legacy LINE identity required")
                legacy.member_id = None
                legacy.ignored = False
                for qualification in sorted(requested):
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
                            granted_by_person_id=actor_person_id,
                            reason=reason,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                thread = self._thread(session, identity.id, now)
                thread.status = "closed"
                thread.closed_at = now
                thread.last_activity_at = now
                thread.updated_at = now
                session.add(
                    AccessAuditRecord(
                        action="person_approved",
                        actor_person_id=actor_person_id,
                        target_person_id=person.id,
                        auth_identity_id=identity.id,
                        before_state={"identity_status": "pending"},
                        after_state={
                            "identity_status": "linked",
                            "qualifications": sorted(requested),
                        },
                        reason=reason,
                        request_id=request_id,
                        created_at=now,
                    )
                )
                subject = identity.provider_subject
            principal = self.resolve_line_principal(subject, now)
            if principal is None:
                raise ConflictError("approved principal did not resolve")
            return principal
        except IntegrityError as error:
            raise ConflictError("non-Member approval conflict") from error

    def set_ignored(
        self,
        actor_person_id: int,
        identity_id: int,
        ignored: bool,
        reason: str,
        request_id: str,
    ) -> AuthIdentity:
        reason = require_reason(reason)
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            self._require_admin(session, actor_person_id)
            identity = session.scalar(
                select(AuthIdentityRecord)
                .where(AuthIdentityRecord.id == identity_id)
                .with_for_update()
            )
            if identity is None or identity.status != "pending" or identity.person_id:
                raise ConflictError("only pending identities may be ignored")
            legacy = session.scalar(
                select(LegacyLineUserRecord)
                .where(LegacyLineUserRecord.line_user_id == identity.provider_subject)
                .with_for_update()
            )
            if legacy is None or legacy.member_id is not None:
                raise ConflictError("unlinked legacy identity required")
            if self._audit_exists(session, request_id):
                if legacy.ignored != ignored:
                    raise ConflictError("idempotent ignore state drift")
                return self._identity(identity)
            if legacy.ignored == ignored:
                raise ConflictError("ignore state is unchanged")
            legacy.ignored = ignored
            session.add(
                AccessAuditRecord(
                    action="identity_ignored" if ignored else "identity_unignored",
                    actor_person_id=actor_person_id,
                    target_person_id=None,
                    auth_identity_id=identity.id,
                    before_state={"ignored": not ignored},
                    after_state={"ignored": ignored},
                    reason=reason,
                    request_id=request_id,
                    created_at=now,
                )
            )
            return self._identity(identity)

    def remap_member_identity(
        self,
        actor_person_id: int,
        identity_id: int,
        target_member_id: int,
        reason: str,
        request_id: str,
        current_identity_id: int | None = None,
    ) -> Principal:
        reason = require_reason(reason)
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            self._require_admin(session, actor_person_id)
            identity = session.scalar(
                select(AuthIdentityRecord)
                .where(AuthIdentityRecord.id == identity_id)
                .with_for_update()
            )
            target_member = session.scalar(
                select(LegacyMemberRecord)
                .where(LegacyMemberRecord.id == target_member_id)
                .with_for_update()
            )
            if (
                identity is None
                or identity.status != "linked"
                or identity.person_id is None
            ):
                raise ConflictError("linked identity required")
            if identity.id == current_identity_id:
                raise ConflictError("cannot remap the current login identity")
            if target_member is None or target_member.person_id is None:
                raise ConflictError("target Member with Person required")
            target = session.scalar(
                select(PersonRecord)
                .where(PersonRecord.id == target_member.person_id)
                .with_for_update()
            )
            if target is None or target.portal_status in {"disabled", "blocked"}:
                raise ConflictError("eligible target Person required")
            if self._audit_exists(session, request_id):
                if identity.person_id != target.id:
                    raise ConflictError("idempotent remap state drift")
                subject = identity.provider_subject
            else:
                old_person_id = identity.person_id
                legacy = session.scalar(
                    select(LegacyLineUserRecord)
                    .where(
                        LegacyLineUserRecord.line_user_id == identity.provider_subject
                    )
                    .with_for_update()
                )
                if legacy is None:
                    raise ConflictError("legacy LINE identity required")
                target_status_before = target.portal_status
                target.portal_status = "active"
                target.version += 1
                target.updated_at = now
                identity.person_id = target.id
                identity.updated_at = now
                legacy.member_id = target_member.id
                legacy.ignored = False
                session.add(
                    AccessAuditRecord(
                        action="identity_remapped",
                        actor_person_id=actor_person_id,
                        target_person_id=target.id,
                        auth_identity_id=identity.id,
                        before_state={
                            "person_id": old_person_id,
                            "target_person_status": target_status_before,
                        },
                        after_state={
                            "person_id": target.id,
                            "member_id": target_member.id,
                            "target_person_status": target.portal_status,
                        },
                        reason=reason,
                        request_id=request_id,
                        created_at=now,
                    )
                )
                subject = identity.provider_subject
        principal = self.resolve_line_principal(subject, now)
        if principal is None:
            raise ConflictError("remapped principal did not resolve")
        return principal

    def set_identity_status(
        self,
        actor_person_id: int,
        identity_id: int,
        status: str,
        reason: str,
        request_id: str,
        current_identity_id: int | None = None,
    ) -> AuthIdentity:
        require_choice(status, IDENTITY_STATUSES, "identity status")
        reason = require_reason(reason)
        now = utc_now()
        actions = {
            "disabled": "identity_disabled",
            "linked": "identity_enabled",
            "pending": "identity_unblocked",
        }
        with Session(self.engine) as session, session.begin():
            self._require_admin(session, actor_person_id)
            identity = session.scalar(
                select(AuthIdentityRecord)
                .where(AuthIdentityRecord.id == identity_id)
                .with_for_update()
            )
            if identity is None:
                raise ConflictError("identity not found")
            if identity.id == current_identity_id and status != identity.status:
                raise ConflictError("cannot change the current login identity")
            if self._audit_exists(session, request_id):
                if identity.status != status:
                    raise ConflictError("idempotent identity state drift")
                return self._identity(identity)
            before = identity.status
            valid = (
                (before == "pending" and status == "blocked")
                or (before == "linked" and status in {"disabled", "blocked"})
                or (
                    before in {"disabled", "blocked"}
                    and status in {"linked", "pending"}
                )
            )
            if not valid:
                raise ConflictError("invalid identity status transition")
            if status == "linked" and identity.person_id is None:
                raise ConflictError("linked identity requires Person")
            if status == "pending" and identity.person_id is not None:
                raise ConflictError("pending identity cannot retain Person")
            identity.status = status
            identity.updated_at = now
            if identity.provider == "line":
                legacy = session.scalar(
                    select(LegacyLineUserRecord)
                    .where(
                        LegacyLineUserRecord.line_user_id == identity.provider_subject
                    )
                    .with_for_update()
                )
                if legacy is not None and identity.person_id is None:
                    legacy.ignored = status == "blocked"
            if status == "blocked" and identity.person_id is None:
                thread = self._thread(session, identity.id, now)
                thread.status = "closed"
                thread.closed_at = now
                thread.last_activity_at = now
                thread.updated_at = now
            elif status == "pending" and identity.person_id is None:
                thread = self._thread(session, identity.id, now)
                thread.status = "open"
                thread.closed_at = None
                thread.last_activity_at = now
                thread.updated_at = now
            session.add(
                AccessAuditRecord(
                    action=(
                        "identity_rejected"
                        if status == "blocked" and identity.person_id is None
                        else (
                            "identity_blocked"
                            if status == "blocked"
                            else actions[status]
                        )
                    ),
                    actor_person_id=actor_person_id,
                    target_person_id=identity.person_id,
                    auth_identity_id=identity.id,
                    before_state={"status": before},
                    after_state={"status": status},
                    reason=reason,
                    request_id=request_id,
                    created_at=now,
                )
            )
            session.flush()
            return self._identity(identity)

    def unlink_identity(
        self,
        actor_person_id: int,
        identity_id: int,
        reason: str,
        request_id: str,
        current_identity_id: int | None = None,
    ) -> AuthIdentity:
        reason = require_reason(reason)
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            self._require_admin(session, actor_person_id)
            identity = session.scalar(
                select(AuthIdentityRecord)
                .where(AuthIdentityRecord.id == identity_id)
                .with_for_update()
            )
            if (
                identity is None
                or identity.status != "linked"
                or identity.person_id is None
            ):
                raise ConflictError("linked identity required")
            if identity.id == current_identity_id:
                raise ConflictError("cannot unlink the current login identity")
            if self._audit_exists(session, request_id):
                raise ConflictError("request already applied")
            before_person_id = identity.person_id
            legacy = session.scalar(
                select(LegacyLineUserRecord)
                .where(LegacyLineUserRecord.line_user_id == identity.provider_subject)
                .with_for_update()
            )
            if legacy is None:
                raise ConflictError("legacy LINE identity required")
            identity.status = "pending"
            identity.person_id = None
            identity.updated_at = now
            legacy.member_id = None
            legacy.ignored = False
            thread = self._thread(session, identity.id, now)
            if thread.status == "closed":
                thread.status = "open"
                thread.closed_at = None
            thread.updated_at = now
            thread.last_activity_at = now
            session.add(
                AccessAuditRecord(
                    action="identity_unlinked",
                    actor_person_id=actor_person_id,
                    target_person_id=before_person_id,
                    auth_identity_id=identity.id,
                    before_state={"status": "linked"},
                    after_state={"status": "pending"},
                    reason=reason,
                    request_id=request_id,
                    created_at=now,
                )
            )
            session.flush()
            return self._identity(identity)

    def change_person_status(
        self,
        actor_person_id: int,
        target_person_id: int,
        status: str,
        reason: str,
        request_id: str,
    ) -> Person:
        reason = require_reason(reason)
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            self._require_admin(session, actor_person_id)
            if actor_person_id == target_person_id:
                raise ConflictError("cannot change own Person status")
            target = session.scalar(
                select(PersonRecord)
                .where(PersonRecord.id == target_person_id)
                .with_for_update()
            )
            if target is None or status not in PERSON_TRANSITIONS.get(
                target.portal_status, ()
            ):
                raise ConflictError("invalid Person status transition")
            if self._audit_exists(session, request_id):
                raise ConflictError("request already applied")
            before = target.portal_status
            if before == "active" and status != "active":
                member = session.scalar(
                    select(LegacyMemberRecord).where(
                        LegacyMemberRecord.person_id == target.id,
                        LegacyMemberRecord.id.in_(self.admin_member_ids or {-1}),
                    )
                )
                if member is not None:
                    remaining = session.scalar(
                        select(func.count(func.distinct(PersonRecord.id)))
                        .join(
                            LegacyMemberRecord,
                            LegacyMemberRecord.person_id == PersonRecord.id,
                        )
                        .join(
                            AuthIdentityRecord,
                            AuthIdentityRecord.person_id == PersonRecord.id,
                        )
                        .where(
                            LegacyMemberRecord.id.in_(self.admin_member_ids or {-1}),
                            PersonRecord.portal_status == "active",
                            AuthIdentityRecord.status == "linked",
                            PersonRecord.id != target.id,
                        )
                    )
                    if not remaining:
                        raise ConflictError(
                            "cannot disable the last active administrator"
                        )
            target.portal_status = status
            target.version += 1
            target.updated_at = now
            session.add(
                AccessAuditRecord(
                    action="status_changed",
                    actor_person_id=actor_person_id,
                    target_person_id=target.id,
                    auth_identity_id=None,
                    before_state={"status": before},
                    after_state={"status": status},
                    reason=reason,
                    request_id=request_id,
                    created_at=now,
                )
            )
            member = session.scalar(
                select(LegacyMemberRecord).where(
                    LegacyMemberRecord.person_id == target.id
                )
            )
            session.flush()
            return self._person(target, member)

    def update_profile(
        self,
        actor_person_id: int,
        target_person_id: int,
        display_name: str,
        request_id: str,
        reason: str = "Person updated their display name",
        formal_name: str | None = None,
        admin_note: str | None = None,
        admin_edit: bool = False,
    ) -> Person:
        display_name = _clean_name(display_name)
        reason = require_reason(reason)
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            if admin_edit:
                self._require_admin(session, actor_person_id)
            elif actor_person_id != target_person_id:
                raise AuthorizationError(
                    "only the Person may update their display name"
                )
            target = session.scalar(
                select(PersonRecord)
                .where(PersonRecord.id == target_person_id)
                .with_for_update()
            )
            if target is None or target.portal_status != "active":
                raise AuthorizationError("active Person required")
            if self._audit_exists(session, request_id):
                member = session.scalar(
                    select(LegacyMemberRecord).where(
                        LegacyMemberRecord.person_id == target.id
                    )
                )
                return self._person(target, member)
            before_display = target.display_name
            target.display_name = display_name
            if admin_edit:
                target.formal_name = (
                    _clean_name(formal_name, "formal name") if formal_name else None
                )
                target.admin_note = _clean_note(admin_note)
            target.version += 1
            target.updated_at = now
            session.add(
                AccessAuditRecord(
                    action="person_profile_updated",
                    actor_person_id=actor_person_id,
                    target_person_id=target.id,
                    auth_identity_id=None,
                    before_state={"display_name": before_display},
                    after_state={"display_name": display_name},
                    reason=reason,
                    request_id=request_id,
                    created_at=now,
                )
            )
            member = session.scalar(
                select(LegacyMemberRecord).where(
                    LegacyMemberRecord.person_id == target.id
                )
            )
            session.flush()
            return self._person(target, member)

    def grant_qualification(
        self,
        actor_person_id: int,
        person_id: int,
        qualification: str,
        reason: str,
        request_id: str,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> None:
        require_choice(qualification, QUALIFICATIONS, "qualification")
        reason = require_reason(reason)
        if qualification == "guest_player":
            validate_guest_period(valid_from, valid_until)
        elif (
            valid_from is not None
            and valid_until is not None
            and valid_until <= valid_from
        ):
            raise ValidationError("qualification validity end must follow start")
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            self._require_admin(session, actor_person_id)
            person = session.scalar(
                select(PersonRecord)
                .where(PersonRecord.id == person_id)
                .with_for_update()
            )
            if person is None or person.portal_status != "active":
                raise ConflictError("active Person required")
            if (
                qualification == "team_player"
                and session.scalar(
                    select(LegacyMemberRecord.id).where(
                        LegacyMemberRecord.person_id == person_id
                    )
                )
                is None
            ):
                raise ConflictError("team_player requires Member link")
            row = session.scalar(
                select(PersonQualificationRecord)
                .where(
                    PersonQualificationRecord.person_id == person_id,
                    PersonQualificationRecord.qualification == qualification,
                )
                .with_for_update()
            )
            if self._audit_exists(session, request_id):
                if row is None or row.status != "active":
                    raise ConflictError("idempotent qualification state drift")
                return
            action = "qualification_granted"
            before = None
            if row is None:
                row = PersonQualificationRecord(
                    person_id=person_id,
                    qualification=qualification,
                    status="active",
                    valid_from=valid_from,
                    valid_until=valid_until,
                    granted_by_person_id=actor_person_id,
                    reason=reason,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            elif row.status == "revoked":
                before = {"status": "revoked"}
                action = "qualification_restored"
                row.status = "active"
                row.valid_from = valid_from
                row.valid_until = valid_until
                row.granted_by_person_id = actor_person_id
                row.reason = reason
                row.updated_at = now
            else:
                raise ConflictError("qualification already active")
            session.add(
                AccessAuditRecord(
                    action=action,
                    actor_person_id=actor_person_id,
                    target_person_id=person_id,
                    auth_identity_id=None,
                    before_state=before,
                    after_state={"qualification": qualification, "status": "active"},
                    reason=reason,
                    request_id=request_id,
                    created_at=now,
                )
            )

    def revoke_qualification(
        self,
        actor_person_id: int,
        person_id: int,
        qualification: str,
        reason: str,
        request_id: str,
    ) -> None:
        require_choice(qualification, QUALIFICATIONS, "qualification")
        reason = require_reason(reason)
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            self._require_admin(session, actor_person_id)
            row = session.scalar(
                select(PersonQualificationRecord)
                .where(
                    PersonQualificationRecord.person_id == person_id,
                    PersonQualificationRecord.qualification == qualification,
                )
                .with_for_update()
            )
            if row is None or row.status != "active":
                raise ConflictError("active qualification required")
            if self._audit_exists(session, request_id):
                raise ConflictError("request already applied")
            row.status = "revoked"
            row.reason = reason
            row.updated_at = now
            session.add(
                AccessAuditRecord(
                    action="qualification_revoked",
                    actor_person_id=actor_person_id,
                    target_person_id=person_id,
                    auth_identity_id=None,
                    before_state={"qualification": qualification, "status": "active"},
                    after_state={"qualification": qualification, "status": "revoked"},
                    reason=reason,
                    request_id=request_id,
                    created_at=now,
                )
            )

    def post_review_message(
        self,
        identity_id: int,
        body: str,
        request_id: str,
        actor_person_id: int | None = None,
        now: datetime | None = None,
    ) -> ReviewMessage:
        now = now or utc_now()
        cleaned = body.strip()
        if not 1 <= len(cleaned) <= 1000:
            raise ValidationError("review message must contain 1 to 1000 characters")
        with Session(self.engine) as session, session.begin():
            identity = session.scalar(
                select(AuthIdentityRecord)
                .where(AuthIdentityRecord.id == identity_id)
                .with_for_update()
            )
            if identity is None or identity.status == "blocked":
                raise AuthorizationError("open pending identity required")
            role = "applicant" if actor_person_id is None else "admin"
            if actor_person_id is not None:
                self._require_admin(session, actor_person_id)
            thread = self._thread(session, identity_id, now)
            if thread.status != "open":
                raise ConflictError("review thread is closed")
            if self._audit_exists(session, request_id):
                raise ConflictError("message request already applied")
            if role == "applicant" and thread.last_applicant_message_at is not None:
                if now < thread.last_applicant_message_at + APPLICANT_MESSAGE_INTERVAL:
                    raise ConflictError(
                        "applicant message is limited to once per 24 hours"
                    )
            message = IdentityReviewMessageRecord(
                thread_id=thread.id,
                sender_role=role,
                sender_person_id=actor_person_id,
                body=cleaned,
                body_redacted=False,
                created_at=now,
            )
            session.add(message)
            if role == "applicant":
                thread.last_applicant_message_at = now
            thread.last_activity_at = now
            thread.updated_at = now
            session.add(
                AccessAuditRecord(
                    action="review_message_sent",
                    actor_person_id=actor_person_id,
                    target_person_id=identity.person_id,
                    auth_identity_id=identity.id,
                    before_state=None,
                    after_state={"sender_role": role},
                    reason="Identity review conversation message",
                    request_id=request_id,
                    created_at=now,
                )
            )
            session.flush()
            return ReviewMessage(message.id, role, cleaned, now)

    def review_messages(self, identity_id: int) -> list[ReviewMessage]:
        with Session(self.engine) as session:
            thread = session.scalar(
                select(IdentityReviewThreadRecord).where(
                    IdentityReviewThreadRecord.auth_identity_id == identity_id
                )
            )
            if thread is None:
                return []
            rows = session.scalars(
                select(IdentityReviewMessageRecord)
                .where(IdentityReviewMessageRecord.thread_id == thread.id)
                .order_by(
                    IdentityReviewMessageRecord.created_at,
                    IdentityReviewMessageRecord.id,
                )
            ).all()
            return [
                ReviewMessage(
                    row.id, row.sender_role, row.body, row.created_at, row.body_redacted
                )
                for row in rows
            ]

    def redact_closed_reviews(
        self, now: datetime | None = None, dry_run: bool = True
    ) -> int:
        now = now or utc_now()
        cutoff = now - REVIEW_RETENTION
        with Session(self.engine) as session, session.begin():
            threads = session.scalars(
                select(IdentityReviewThreadRecord)
                .where(
                    IdentityReviewThreadRecord.status == "closed",
                    IdentityReviewThreadRecord.closed_at <= cutoff,
                    IdentityReviewThreadRecord.redacted_at.is_(None),
                )
                .with_for_update()
            ).all()
            if dry_run:
                return len(threads)
            for thread in threads:
                messages = session.scalars(
                    select(IdentityReviewMessageRecord).where(
                        IdentityReviewMessageRecord.thread_id == thread.id
                    )
                ).all()
                for message in messages:
                    message.body = None
                    message.body_redacted = True
                thread.redacted_at = now
                thread.updated_at = now
                session.add(
                    AccessAuditRecord(
                        action="review_redacted",
                        actor_person_id=None,
                        target_person_id=None,
                        auth_identity_id=thread.auth_identity_id,
                        before_state={"body_redacted": False},
                        after_state={"body_redacted": True},
                        reason="Identity review retention elapsed",
                        request_id=f"phase-c-review-redact-{thread.id}",
                        created_at=now,
                    )
                )
            return len(threads)

    @staticmethod
    def _eligibility_in_session(
        session: Session, person: PersonRecord | None, game_start: datetime
    ) -> tuple[bool, str | None]:
        if person is None or person.portal_status != "active":
            return False, None
        rows = session.scalars(
            select(PersonQualificationRecord).where(
                PersonQualificationRecord.person_id == person.id,
                PersonQualificationRecord.qualification.in_(
                    ("team_player", "guest_player")
                ),
            )
        ).all()
        active = {
            row.qualification
            for row in rows
            if is_qualification_active(
                row.status, row.valid_from, row.valid_until, game_start
            )
        }
        if "team_player" in active:
            return True, "team_player"
        if "guest_player" in active:
            return True, "guest_player"
        return False, None

    def can_reply_to_game(
        self, person_id: int, game_start: datetime
    ) -> tuple[bool, str | None]:
        with Session(self.engine) as session:
            person = session.get(PersonRecord, person_id)
            return self._eligibility_in_session(session, person, game_start)

    def reply_to_game(
        self, person_id: int, game_id: int, reply: int, user_id: int | None = None
    ) -> bool:
        if reply not in {1, 2, 3, 4, 5}:
            raise ValidationError("invalid legacy attendance reply")
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            person = session.scalar(
                select(PersonRecord)
                .where(PersonRecord.id == person_id)
                .with_for_update()
            )
            game = session.get(LegacyGameRecord, game_id)
            if person is None or person.portal_status != "active" or game is None:
                raise AuthorizationError("active Person and game required")
            if (
                game.start_datetime is None
                or game.start_datetime <= now
                or game.cancellation_time
            ):
                raise ConflictError("open future game required")
            eligible, _ = self._eligibility_in_session(
                session, person, game.start_datetime
            )
            if not eligible:
                raise AuthorizationError("active team or guest qualification required")
            latest = session.scalar(
                select(LegacyGameAttendanceReplyRecord)
                .where(
                    LegacyGameAttendanceReplyRecord.game_id == game_id,
                    LegacyGameAttendanceReplyRecord.person_id == person_id,
                )
                .order_by(
                    LegacyGameAttendanceReplyRecord.updated_at.desc(),
                    LegacyGameAttendanceReplyRecord.id.desc(),
                )
                .limit(1)
                .with_for_update()
            )
            if latest is not None and latest.reply == reply:
                return False
            member_id = session.scalar(
                select(LegacyMemberRecord.id).where(
                    LegacyMemberRecord.person_id == person_id
                )
            )
            session.add(
                LegacyGameAttendanceReplyRecord(
                    game_id=game_id,
                    user_id=user_id,
                    member_id=member_id,
                    person_id=person_id,
                    reply=reply,
                    updated_at=now,
                )
            )
            return True

    def attendance_summary(
        self, game_id: int, use_display_name: bool = False
    ) -> AttendanceSummary:
        with Session(self.engine) as session:
            game = session.get(LegacyGameRecord, game_id)
            if game is None or game.start_datetime is None:
                raise ConflictError("game not found")
            rows = session.execute(
                select(
                    LegacyGameAttendanceReplyRecord,
                    PersonRecord,
                    LegacyMemberRecord,
                )
                .outerjoin(
                    LegacyMemberRecord,
                    LegacyMemberRecord.id == LegacyGameAttendanceReplyRecord.member_id,
                )
                .join(
                    PersonRecord,
                    PersonRecord.id
                    == func.coalesce(
                        LegacyGameAttendanceReplyRecord.person_id,
                        LegacyMemberRecord.person_id,
                    ),
                )
                .where(
                    LegacyGameAttendanceReplyRecord.game_id == game_id,
                    or_(
                        LegacyGameAttendanceReplyRecord.member_id.is_(None),
                        LegacyGameAttendanceReplyRecord.person_id.is_(None),
                        LegacyMemberRecord.person_id
                        == LegacyGameAttendanceReplyRecord.person_id,
                    ),
                )
                .order_by(
                    func.coalesce(
                        LegacyGameAttendanceReplyRecord.person_id,
                        LegacyMemberRecord.person_id,
                    ),
                    LegacyGameAttendanceReplyRecord.updated_at.desc(),
                    LegacyGameAttendanceReplyRecord.id.desc(),
                )
            ).all()
            latest = {}
            for reply, person, member in rows:
                latest.setdefault(person.id, (reply, person, member))
            participants = []
            for person_id, (reply, person, member) in latest.items():
                eligible, category = self._eligibility_in_session(
                    session, person, game.start_datetime
                )
                if not eligible:
                    continue
                if category == "guest_player" and reply.reply == 5:
                    continue
                name = (
                    person.display_name
                    if use_display_name
                    else (member.name if member else person.formal_name)
                    or person.display_name
                )
                participants.append(
                    {
                        "person_id": person_id,
                        "member_id": member.id if member else None,
                        "name": name,
                        "reply": reply.reply,
                        "qualification": category,
                    }
                )
            team_qualifications = session.scalars(
                select(PersonQualificationRecord)
                .join(
                    PersonRecord, PersonRecord.id == PersonQualificationRecord.person_id
                )
                .where(
                    PersonQualificationRecord.qualification == "team_player",
                    PersonRecord.portal_status == "active",
                )
            ).all()
            team_ids = {
                qualification.person_id
                for qualification in team_qualifications
                if is_qualification_active(
                    qualification.status,
                    qualification.valid_from,
                    qualification.valid_until,
                    game.start_datetime,
                )
            }
            replied_team = sum(item["person_id"] in team_ids for item in participants)
            return AttendanceSummary(tuple(participants), len(team_ids), replied_team)
