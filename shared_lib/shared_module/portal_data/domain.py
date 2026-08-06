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

    @property
    def can_use_portal(self) -> bool:
        return self.status == "active" and self.access_level in ACCESS_LEVELS

    @property
    def can_manage_events(self) -> bool:
        return self.can_use_portal and self.access_level in {"officer", "admin"}

    @property
    def is_admin(self) -> bool:
        return self.can_use_portal and self.access_level == "admin"


@dataclass(frozen=True)
class AuthIdentity:
    id: int
    provider: str
    provider_subject: str
    status: str
    person_id: int | None


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
