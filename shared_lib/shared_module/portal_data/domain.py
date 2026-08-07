from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

ACCESS_LEVELS = frozenset({"basic", "officer", "admin"})
PORTAL_STATUSES = frozenset({"pending", "active", "disabled", "inactive", "blocked"})
QUALIFICATIONS = frozenset({"team_player", "guest_player", "affiliate", "staff"})
IDENTITY_PROVIDERS = frozenset({"line", "google", "apple"})
ATTENDANCE_REPLIES = frozenset({"attending", "not_attending", "maybe"})


class PortalDataError(RuntimeError):
    pass


class AuthorizationError(PortalDataError):
    pass


class ConflictError(PortalDataError):
    pass


class ValidationError(PortalDataError):
    pass


@dataclass(frozen=True)
class Person:
    id: int
    display_name: str
    access_level: str
    status: str
    formal_name: str | None = None
    member_id: int | None = None

    @property
    def can_use_portal(self) -> bool:
        return self.status == "active" and self.access_level in ACCESS_LEVELS

    @property
    def can_manage_events(self) -> bool:
        return self.can_use_portal and self.access_level in {"officer", "admin"}

    @property
    def is_admin(self) -> bool:
        return self.can_use_portal and self.access_level == "admin"

    def preferred_name(self, use_display_name: bool = False) -> str:
        if use_display_name:
            return self.display_name
        return self.formal_name or self.display_name

    @property
    def name(self) -> str:
        """Compatibility label for legacy attendance templates."""
        return self.preferred_name()


@dataclass(frozen=True)
class AuthIdentity:
    id: int
    provider: str
    provider_subject: str
    status: str
    person_id: int | None


@dataclass(frozen=True)
class Principal:
    person: Person
    identity: AuthIdentity
    qualifications: frozenset[str]

    @property
    def can_reply_as_team_player(self) -> bool:
        return self.person.can_use_portal and "team_player" in self.qualifications


@dataclass(frozen=True)
class AttendanceParticipant:
    person_id: int
    name: str
    reply: int
    qualification: str
    member_id: int | None = None


@dataclass(frozen=True)
class ReviewMessage:
    id: int
    sender_role: str
    body: str | None
    created_at: datetime
    redacted: bool = False


@dataclass(frozen=True)
class Invitee:
    event_id: int
    person_id: int
    included: bool
    source: str
    participation_category: str


@dataclass(frozen=True)
class BackfillSummary:
    scanned_members: int
    created_people: int
    linked_members: int
    granted_team_players: int
    promoted_fake_admins: int
    orphan_count: int = 0
    collision_count: int = 0


def require_choice(value: str, allowed: frozenset[str], field: str) -> str:
    if value not in allowed:
        raise ValidationError(f"unknown {field}")
    return value


def require_reason(value: str) -> str:
    cleaned = value.strip()
    if not 3 <= len(cleaned) <= 300:
        raise ValidationError("reason must contain 3 to 300 characters")
    return cleaned


def is_qualification_active(
    status: str,
    valid_from: datetime | None,
    valid_until: datetime | None,
    now: datetime,
) -> bool:
    if status != "active":
        return False
    if valid_from is not None and valid_from > now:
        return False
    if valid_until is not None and valid_until <= now:
        return False
    return True


def validate_guest_period(
    valid_from: datetime | None, valid_until: datetime | None
) -> None:
    if valid_from is None or valid_until is None:
        raise ValidationError("guest_player requires a bounded validity period")
    if valid_from.tzinfo is None or valid_until.tzinfo is None:
        raise ValidationError("guest_player validity must be timezone-aware")
    if valid_until <= valid_from:
        raise ValidationError("guest_player validity end must follow start")
    try:
        maximum_until = valid_from.replace(year=valid_from.year + 5)
    except ValueError:
        maximum_until = valid_from.replace(year=valid_from.year + 5, day=28)
    if valid_until > maximum_until:
        raise ValidationError("guest_player validity cannot exceed five years")
