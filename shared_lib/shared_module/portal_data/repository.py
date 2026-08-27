from __future__ import annotations

import copy
import hashlib
import json
import threading
from collections import Counter
from datetime import datetime, timezone
from typing import Iterable, Protocol

from sqlalchemy import Engine, and_, delete, func, or_, select, text, update
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
    ValidationError,
    is_qualification_active,
    require_choice,
    require_reason,
    validate_guest_period,
)
from .models import (
    AccessAuditRecord,
    ActivityRecord,
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

EVENT_TYPES = frozenset({"game", "meal", "trip", "practice", "social", "other"})
ACTIVITY_TYPES = frozenset(
    {"game", "meal", "transport", "lodging", "gathering", "other"}
)


def _bounded_text(value: str, field: str, maximum: int = 200) -> str:
    cleaned = value.strip()
    if not 1 <= len(cleaned) <= maximum:
        raise ValidationError(f"{field} must contain 1 to {maximum} characters")
    return cleaned


def _event_times(start_at: datetime, end_at: datetime | None) -> None:
    if start_at.tzinfo is None or (end_at is not None and end_at.tzinfo is None):
        raise ValidationError("event timestamps must be timezone-aware")
    if end_at is not None and end_at <= start_at:
        raise ValidationError("event end must follow start")


def _request_id(value: str) -> str:
    cleaned = value.strip()
    if not 1 <= len(cleaned) <= 100:
        raise ValidationError("request id must contain 1 to 100 characters")
    return cleaned


def _operation_details(
    operation: str, payload: dict, *, target_id: int | None = None
) -> dict:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda value: (
            value.isoformat() if isinstance(value, datetime) else value
        ),
    ).encode("utf-8")
    details = {
        "operation": operation,
        "fingerprint": hashlib.sha256(encoded).hexdigest(),
    }
    if target_id is not None:
        details["target_id"] = target_id
    return details


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
        end_at: datetime | None = None,
    ) -> int: ...

    def managed_events(self, actor_id: int) -> tuple[dict, ...]: ...
    def managed_event(self, actor_id: int, event_id: int) -> dict: ...
    def eligibility_preview(self, actor_id: int, event_id: int) -> dict: ...

    def update_event(
        self,
        actor_id: int,
        event_id: int,
        title: str,
        event_type: str,
        start_at: datetime,
        end_at: datetime | None,
        eligibility: Iterable[str],
        expected_version: int,
        request_id: str,
    ) -> dict: ...

    def add_activity(
        self,
        actor_id: int,
        event_id: int,
        title: str,
        activity_type: str,
        start_at: datetime,
        end_at: datetime | None,
        request_id: str | None = None,
    ) -> int: ...

    def update_activity(
        self,
        actor_id: int,
        event_id: int,
        activity_id: int,
        title: str,
        activity_type: str,
        start_at: datetime,
        end_at: datetime | None,
        request_id: str,
    ) -> None: ...

    def delete_activity(
        self,
        actor_id: int,
        event_id: int,
        activity_id: int,
        request_id: str | None = None,
    ) -> None: ...

    def move_activity(
        self,
        actor_id: int,
        event_id: int,
        activity_id: int,
        direction: str,
        request_id: str | None = None,
    ) -> None: ...

    def cancel_event(self, actor_id: int, event_id: int, request_id: str) -> dict: ...
    def event_audits(self, event_id: int) -> tuple[dict, ...]: ...

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
        request_id: str,
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
        self.activities: dict[int, dict] = {}
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
        with self._lock:
            self.get_person(person_id)
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
        with self._lock:
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
        end_at: datetime | None = None,
    ) -> int:
        title = _bounded_text(title, "event title")
        require_choice(event_type, EVENT_TYPES, "event type")
        _event_times(start_at, end_at)
        rules = {
            require_choice(value, QUALIFICATIONS, "qualification")
            for value in eligibility
        }
        if not rules:
            raise ConflictError("event eligibility cannot be empty")
        with self._lock:
            self._require_event_manager(actor_id)
            event_id = self._next("event")
            self.events[event_id] = {
                "id": event_id,
                "title": title,
                "event_type": event_type,
                "start_at": start_at,
                "end_at": end_at,
                "status": "draft",
                "eligibility": rules,
                "version": 1,
                "created_by_person_id": actor_id,
                "published_at": None,
            }
            return event_id

    def _event_for_manager(self, actor_id: int, event_id: int) -> dict:
        self._require_event_manager(actor_id)
        event = self.events.get(event_id)
        if event is None:
            raise ConflictError("event not found")
        return event

    def _event_projection(self, event: dict) -> dict:
        event_id = event["id"]
        return {
            **copy.deepcopy(event),
            "eligibility": tuple(sorted(event["eligibility"])),
            "activities": tuple(
                copy.deepcopy(activity)
                for activity in sorted(
                    (
                        row
                        for row in self.activities.values()
                        if row["event_id"] == event_id
                    ),
                    key=lambda row: (row["position"], row["id"]),
                )
            ),
        }

    def managed_events(self, actor_id: int) -> tuple[dict, ...]:
        self._require_event_manager(actor_id)
        return tuple(
            self._event_projection(event)
            for event in sorted(
                self.events.values(), key=lambda row: (row["start_at"], row["id"])
            )
        )

    def managed_event(self, actor_id: int, event_id: int) -> dict:
        return self._event_projection(self._event_for_manager(actor_id, event_id))

    def eligibility_preview(self, actor_id: int, event_id: int) -> dict:
        event = self._event_for_manager(actor_id, event_id)
        counts: Counter[str] = Counter()
        candidates = []
        eligible_person_ids = set()
        for person in self.people.values():
            if not person.can_use_portal:
                continue
            matches = self.qualifications_for_person(person.id) & event["eligibility"]
            if matches:
                eligible_person_ids.add(person.id)
                for qualification in matches:
                    counts[qualification] += 1
            candidates.append(
                {"person_id": person.id, "display_name": person.display_name}
            )
        return {
            "qualification_counts": dict(sorted(counts.items())),
            "candidate_count": len(eligible_person_ids),
            "candidates": tuple(sorted(candidates, key=lambda row: row["person_id"])),
            "override_targets": tuple(
                {"person_id": person.id, "display_name": person.display_name}
                for person in sorted(self.people.values(), key=lambda row: row.id)
                if person.can_use_portal
            ),
            "overrides": tuple(
                {
                    "person_id": person_id,
                    "action": override["action"],
                    "participation_category": override["category"],
                    "reason": override["reason"],
                }
                for (target_event_id, person_id), override in sorted(
                    self.overrides.items()
                )
                if target_event_id == event_id
            ),
        }

    def _append_event_audit(
        self,
        actor_id: int,
        event_id: int,
        action: str,
        request_id: str,
        details: dict | None = None,
        reason: str | None = None,
    ) -> bool:
        request_id = _request_id(request_id)
        if request_id in self.audit_requests:
            existing = next(
                row for row in self.audits if row.get("request_id") == request_id
            )
            if (
                existing.get("event_id") == event_id
                and existing.get("actor") == actor_id
                and existing.get("action") == action
                and existing.get("details") == details
                and existing.get("reason") == reason
            ):
                return False
            raise ConflictError("event request id already used")
        self.audits.append(
            {
                "event_id": event_id,
                "actor": actor_id,
                "action": action,
                "request_id": request_id,
                "details": copy.deepcopy(details),
                "reason": reason,
            }
        )
        self.audit_requests.add(request_id)
        return True

    def update_event(
        self,
        actor_id: int,
        event_id: int,
        title: str,
        event_type: str,
        start_at: datetime,
        end_at: datetime | None,
        eligibility: Iterable[str],
        expected_version: int,
        request_id: str,
    ) -> dict:
        title = _bounded_text(title, "event title")
        require_choice(event_type, EVENT_TYPES, "event type")
        _event_times(start_at, end_at)
        rules = {
            require_choice(value, QUALIFICATIONS, "qualification")
            for value in eligibility
        }
        if not rules:
            raise ConflictError("event eligibility cannot be empty")
        details = _operation_details(
            "event_update",
            {
                "title": title,
                "event_type": event_type,
                "start_at": start_at,
                "end_at": end_at,
                "eligibility": sorted(rules),
                "expected_version": expected_version,
            },
            target_id=event_id,
        )
        with self._lock:
            event = self._event_for_manager(actor_id, event_id)
            if event["status"] == "published" and request_id in self.audit_requests:
                if not self._append_event_audit(
                    actor_id, event_id, "edited", request_id, details
                ):
                    return self._event_projection(event)
            if event["status"] == "cancelled":
                raise ConflictError("cancelled event cannot be edited")
            if (
                type(expected_version) is not int
                or event["version"] != expected_version
            ):
                raise ConflictError("event version conflict")
            if event["status"] == "published" and not self._append_event_audit(
                actor_id,
                event_id,
                "edited",
                request_id,
                details,
            ):
                return self._event_projection(event)
            event.update(
                title=title,
                event_type=event_type,
                start_at=start_at,
                end_at=end_at,
                version=event["version"] + 1,
            )
            if event["status"] == "draft":
                event["eligibility"] = rules
            return self._event_projection(event)

    def add_activity(
        self,
        actor_id: int,
        event_id: int,
        title: str,
        activity_type: str,
        start_at: datetime,
        end_at: datetime | None,
        request_id: str | None = None,
    ) -> int:
        title = _bounded_text(title, "activity title")
        require_choice(activity_type, ACTIVITY_TYPES, "activity type")
        _event_times(start_at, end_at)
        details = _operation_details(
            "activity_add",
            {
                "title": title,
                "activity_type": activity_type,
                "start_at": start_at,
                "end_at": end_at,
            },
        )
        with self._lock:
            event = self._event_for_manager(actor_id, event_id)
            if event["status"] == "cancelled":
                raise ConflictError("cancelled event cannot be edited")
            if event["status"] == "published":
                if request_id is None:
                    raise ConflictError("published edit request id required")
                request_id = _request_id(request_id)
                if request_id in self.audit_requests:
                    existing = next(
                        row
                        for row in self.audits
                        if row.get("request_id") == request_id
                    )
                    if (
                        existing.get("event_id") == event_id
                        and existing.get("actor") == actor_id
                        and existing.get("action") == "edited"
                        and existing.get("details", {}).get("operation")
                        == details["operation"]
                        and existing.get("details", {}).get("fingerprint")
                        == details["fingerprint"]
                    ):
                        return existing["details"]["target_id"]
                    raise ConflictError("event request id already used")
            positions = [
                row["position"]
                for row in self.activities.values()
                if row["event_id"] == event_id
            ]
            activity_id = self._next("activity")
            self.activities[activity_id] = {
                "id": activity_id,
                "event_id": event_id,
                "title": title,
                "activity_type": activity_type,
                "position": max(positions, default=0) + 1,
                "start_at": start_at,
                "end_at": end_at,
                "game_id": None,
            }
            if event["status"] == "published":
                self._append_event_audit(
                    actor_id,
                    event_id,
                    "edited",
                    request_id,
                    {**details, "target_id": activity_id},
                )
            event["version"] += 1
            return activity_id

    def _activity_for_event(self, event_id: int, activity_id: int) -> dict:
        activity = self.activities.get(activity_id)
        if activity is None or activity["event_id"] != event_id:
            raise ConflictError("activity does not belong to event")
        return activity

    def update_activity(
        self,
        actor_id: int,
        event_id: int,
        activity_id: int,
        title: str,
        activity_type: str,
        start_at: datetime,
        end_at: datetime | None,
        request_id: str,
    ) -> None:
        title = _bounded_text(title, "activity title")
        require_choice(activity_type, ACTIVITY_TYPES, "activity type")
        _event_times(start_at, end_at)
        details = _operation_details(
            "activity_update",
            {
                "title": title,
                "activity_type": activity_type,
                "start_at": start_at,
                "end_at": end_at,
            },
            target_id=activity_id,
        )
        with self._lock:
            event = self._event_for_manager(actor_id, event_id)
            activity = self._activity_for_event(event_id, activity_id)
            if event["status"] == "cancelled":
                raise ConflictError("cancelled event cannot be edited")
            if event["status"] == "published" and not self._append_event_audit(
                actor_id, event_id, "edited", request_id, details
            ):
                return
            activity.update(
                title=title,
                activity_type=activity_type,
                start_at=start_at,
                end_at=end_at,
            )
            event["version"] += 1

    def _normalize_activity_positions(self, event_id: int) -> None:
        rows = sorted(
            (row for row in self.activities.values() if row["event_id"] == event_id),
            key=lambda row: (row["position"], row["id"]),
        )
        for position, row in enumerate(rows, 1):
            row["position"] = position

    def delete_activity(
        self,
        actor_id: int,
        event_id: int,
        activity_id: int,
        request_id: str | None = None,
    ) -> None:
        details = _operation_details("activity_delete", {}, target_id=activity_id)
        with self._lock:
            event = self._event_for_manager(actor_id, event_id)
            if event["status"] == "cancelled":
                raise ConflictError("cancelled event cannot be edited")
            if event["status"] == "published":
                if request_id is None:
                    raise ConflictError("published edit request id required")
                if not self._append_event_audit(
                    actor_id, event_id, "edited", request_id, details
                ):
                    return
            self._activity_for_event(event_id, activity_id)
            del self.activities[activity_id]
            self._normalize_activity_positions(event_id)
            event["version"] += 1

    def move_activity(
        self,
        actor_id: int,
        event_id: int,
        activity_id: int,
        direction: str,
        request_id: str | None = None,
    ) -> None:
        if direction not in {"up", "down"}:
            raise ConflictError("invalid activity direction")
        details = _operation_details(
            "activity_move", {"direction": direction}, target_id=activity_id
        )
        with self._lock:
            event = self._event_for_manager(actor_id, event_id)
            activity = self._activity_for_event(event_id, activity_id)
            if event["status"] == "cancelled":
                raise ConflictError("cancelled event cannot be edited")
            if event["status"] == "published":
                if request_id is None:
                    raise ConflictError("published edit request id required")
                request_id = _request_id(request_id)
                if request_id in self.audit_requests:
                    if not self._append_event_audit(
                        actor_id, event_id, "edited", request_id, details
                    ):
                        return
            rows = sorted(
                (
                    row
                    for row in self.activities.values()
                    if row["event_id"] == event_id
                ),
                key=lambda row: (row["position"], row["id"]),
            )
            index = rows.index(activity)
            target_index = index + (-1 if direction == "up" else 1)
            if target_index < 0 or target_index >= len(rows):
                return
            if event["status"] == "published":
                if not self._append_event_audit(
                    actor_id, event_id, "edited", request_id, details
                ):
                    return
            rows[index]["position"], rows[target_index]["position"] = (
                rows[target_index]["position"],
                rows[index]["position"],
            )
            event["version"] += 1

    def cancel_event(self, actor_id: int, event_id: int, request_id: str) -> dict:
        with self._lock:
            event = self._event_for_manager(actor_id, event_id)
            if request_id in self.audit_requests:
                if not self._append_event_audit(
                    actor_id, event_id, "cancelled", request_id
                ):
                    return self._event_projection(event)
            if event["status"] == "cancelled":
                return self._event_projection(event)
            if event["status"] != "published":
                raise ConflictError("published event required")
            if not self._append_event_audit(
                actor_id, event_id, "cancelled", request_id
            ):
                return self._event_projection(event)
            event["status"] = "cancelled"
            event["version"] += 1
            return self._event_projection(event)

    def event_audits(self, event_id: int) -> tuple[dict, ...]:
        return tuple(
            copy.deepcopy(row) for row in self.audits if row.get("event_id") == event_id
        )

    def set_invitee_override(
        self,
        actor_id: int,
        event_id: int,
        person_id: int,
        action: str,
        participation_category: str,
        reason: str,
        request_id: str,
    ) -> None:
        if action not in {"include", "exclude"}:
            raise ConflictError("invalid override")
        if participation_category not in QUALIFICATIONS | {"other"}:
            raise ConflictError("invalid participation category")
        reason = require_reason(reason)
        details = _operation_details(
            "override",
            {
                "person_id": person_id,
                "action": action,
                "participation_category": participation_category,
                "reason": reason,
            },
            target_id=person_id,
        )
        with self._lock:
            self._require_event_manager(actor_id)
            self.get_person(person_id)
            if self.events.get(event_id, {}).get("status") != "draft":
                raise ConflictError("only draft events accept overrides")
            if not self._append_event_audit(
                actor_id,
                event_id,
                "invitee_included" if action == "include" else "invitee_excluded",
                request_id,
                details,
                reason,
            ):
                return
            self.overrides[(event_id, person_id)] = {
                "action": action,
                "category": participation_category,
                "actor": actor_id,
                "reason": reason,
            }

    def publish_event(
        self, actor_id: int, event_id: int, request_id: str
    ) -> list[Invitee]:
        with self._lock:
            self._require_event_manager(actor_id)
            event = self.events.get(event_id)
            if event is None:
                raise ConflictError("event not found")
            request_id = _request_id(request_id)
            details = _operation_details(
                "publish", {"eligibility": sorted(event["eligibility"])}
            )
            if request_id in self.audit_requests:
                existing = next(
                    row for row in self.audits if row.get("request_id") == request_id
                )
                if (
                    existing.get("event_id") == event_id
                    and existing.get("actor") == actor_id
                    and existing.get("action") == "published"
                    and existing.get("details") == details
                ):
                    return self.event_invitees(event_id)
                raise ConflictError("event request id already used")
            if event["status"] == "published":
                return self.event_invitees(event_id)
            if event["status"] != "draft":
                raise ConflictError("draft event required")
            now = utc_now()
            snapshot_invitees = {}
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
                    snapshot_invitees[(event_id, person.id)] = Invitee(
                        event_id, person.id, True, "qualification", category
                    )
            for (override_event_id, person_id), override in self.overrides.items():
                if override_event_id != event_id:
                    continue
                snapshot_invitees[(event_id, person_id)] = Invitee(
                    event_id,
                    person_id,
                    override["action"] == "include",
                    f"manual_{override['action']}",
                    override["category"],
                )
            next_invitees = dict(self.invitees)
            next_invitees.update(snapshot_invitees)
            next_event = copy.deepcopy(event)
            next_event["status"] = "published"
            next_event["published_at"] = now
            next_event["version"] += 1
            next_audits = list(self.audits)
            next_audits.append(
                {
                    "event_id": event_id,
                    "actor": actor_id,
                    "action": "published",
                    "request_id": request_id,
                    "details": details,
                    "reason": None,
                }
            )
            next_audit_requests = set(self.audit_requests)
            next_audit_requests.add(request_id)
            next_events = dict(self.events)
            next_events[event_id] = next_event
            self.invitees = next_invitees
            self.audits = next_audits
            self.audit_requests = next_audit_requests
            self.events = next_events
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
    EVENT_SNAPSHOT_LOCK_KEY = ADMIN_LOCK_KEY + 0x100000

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
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": self.EVENT_SNAPSHOT_LOCK_KEY},
            )
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
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": self.EVENT_SNAPSHOT_LOCK_KEY},
            )
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
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": self.EVENT_SNAPSHOT_LOCK_KEY},
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
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": self.EVENT_SNAPSHOT_LOCK_KEY},
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
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": self.EVENT_SNAPSHOT_LOCK_KEY},
            )
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
        end_at: datetime | None = None,
    ) -> int:
        title = _bounded_text(title, "event title")
        require_choice(event_type, EVENT_TYPES, "event type")
        _event_times(start_at, end_at)
        rules = {
            require_choice(value, QUALIFICATIONS, "qualification")
            for value in eligibility
        }
        if not rules:
            raise ConflictError("event eligibility cannot be empty")
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": self.EVENT_SNAPSHOT_LOCK_KEY},
            )
            self._require_event_manager(session, actor_id)
            event = EventRecord(
                title=title,
                event_type=event_type,
                status="draft",
                start_at=start_at,
                end_at=end_at,
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

    @staticmethod
    def _managed_event_projection(
        event: EventRecord,
        activities: Iterable[ActivityRecord],
        eligibility: Iterable[str],
    ) -> dict:
        return {
            "id": event.id,
            "title": event.title,
            "event_type": event.event_type,
            "status": event.status,
            "start_at": event.start_at,
            "end_at": event.end_at,
            "published_at": event.published_at,
            "version": event.version,
            "created_by_person_id": event.created_by_person_id,
            "eligibility": tuple(sorted(eligibility)),
            "activities": tuple(
                {
                    "id": row.id,
                    "event_id": row.event_id,
                    "title": row.title,
                    "activity_type": row.activity_type,
                    "position": row.position,
                    "start_at": row.start_at,
                    "end_at": row.end_at,
                    "game_id": row.game_id,
                }
                for row in activities
            ),
        }

    def _managed_event_in_session(self, session: Session, event_id: int) -> dict:
        event = session.get(EventRecord, event_id)
        if event is None:
            raise ConflictError("event not found")
        activities = session.scalars(
            select(ActivityRecord)
            .where(ActivityRecord.event_id == event_id)
            .order_by(ActivityRecord.position, ActivityRecord.id)
        ).all()
        eligibility = session.scalars(
            select(EventEligibilityRuleRecord.qualification).where(
                EventEligibilityRuleRecord.event_id == event_id
            )
        ).all()
        return self._managed_event_projection(event, activities, eligibility)

    def managed_events(self, actor_id: int) -> tuple[dict, ...]:
        with Session(self.engine) as session:
            self._require_event_manager(session, actor_id)
            events = session.scalars(
                select(EventRecord).order_by(EventRecord.start_at, EventRecord.id)
            ).all()
            return tuple(
                self._managed_event_in_session(session, event.id) for event in events
            )

    def managed_event(self, actor_id: int, event_id: int) -> dict:
        with Session(self.engine) as session:
            self._require_event_manager(session, actor_id)
            return self._managed_event_in_session(session, event_id)

    def eligibility_preview(self, actor_id: int, event_id: int) -> dict:
        now = utc_now()
        with Session(self.engine) as session:
            self._require_event_manager(session, actor_id)
            event = session.get(EventRecord, event_id)
            if event is None:
                raise ConflictError("event not found")
            rules = set(
                session.scalars(
                    select(EventEligibilityRuleRecord.qualification).where(
                        EventEligibilityRuleRecord.event_id == event_id
                    )
                )
            )
            rows = session.execute(
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
                .order_by(PersonQualificationRecord.person_id)
            ).all()
            counts = Counter(qualification for _, qualification in rows)
            eligible_person_ids = {row[0] for row in rows}
            overrides = session.scalars(
                select(EventInviteeOverrideRecord)
                .where(EventInviteeOverrideRecord.event_id == event_id)
                .order_by(EventInviteeOverrideRecord.person_id)
            ).all()
            override_targets = session.execute(
                select(PersonRecord.id, PersonRecord.display_name)
                .where(
                    PersonRecord.portal_status == "active",
                    PersonRecord.portal_access_level.in_(ACCESS_LEVELS),
                )
                .order_by(PersonRecord.id)
            ).all()
            candidates = tuple(
                {"person_id": person_id, "display_name": display_name}
                for person_id, display_name in override_targets
            )
            return {
                "qualification_counts": dict(sorted(counts.items())),
                "candidate_count": len(eligible_person_ids),
                "candidates": candidates,
                "override_targets": tuple(dict(candidate) for candidate in candidates),
                "overrides": tuple(
                    {
                        "person_id": row.person_id,
                        "action": row.action,
                        "participation_category": row.participation_category,
                        "reason": row.reason,
                    }
                    for row in overrides
                ),
            }

    @staticmethod
    def _existing_event_audit(
        session: Session, request_id: str
    ) -> EventAuditRecord | None:
        return session.scalar(
            select(EventAuditRecord).where(EventAuditRecord.request_id == request_id)
        )

    @staticmethod
    def _add_event_audit(
        session: Session,
        *,
        event_id: int,
        actor_id: int,
        action: str,
        request_id: str,
        details: dict | None = None,
        reason: str | None = None,
    ) -> None:
        session.add(
            EventAuditRecord(
                event_id=event_id,
                actor_person_id=actor_id,
                action=action,
                reason=reason or f"event {action} by authorized manager",
                request_id=request_id,
                details=details,
                created_at=utc_now(),
            )
        )

    def update_event(
        self,
        actor_id: int,
        event_id: int,
        title: str,
        event_type: str,
        start_at: datetime,
        end_at: datetime | None,
        eligibility: Iterable[str],
        expected_version: int,
        request_id: str,
    ) -> dict:
        title = _bounded_text(title, "event title")
        require_choice(event_type, EVENT_TYPES, "event type")
        _event_times(start_at, end_at)
        request_id = _request_id(request_id)
        rules = {
            require_choice(value, QUALIFICATIONS, "qualification")
            for value in eligibility
        }
        if not rules:
            raise ConflictError("event eligibility cannot be empty")
        details = _operation_details(
            "event_update",
            {
                "title": title,
                "event_type": event_type,
                "start_at": start_at,
                "end_at": end_at,
                "eligibility": sorted(rules),
                "expected_version": expected_version,
            },
            target_id=event_id,
        )
        with Session(self.engine) as session, session.begin():
            self._require_event_manager(session, actor_id)
            event = session.scalar(
                select(EventRecord).where(EventRecord.id == event_id).with_for_update()
            )
            if event is None:
                raise ConflictError("event not found")
            existing = self._existing_event_audit(session, request_id)
            if existing is not None:
                if (
                    existing.event_id == event_id
                    and existing.actor_person_id == actor_id
                    and existing.action == "edited"
                    and existing.details == details
                ):
                    return self._managed_event_in_session(session, event_id)
                raise ConflictError("event request id already used")
            if event.status == "cancelled":
                raise ConflictError("cancelled event cannot be edited")
            if type(expected_version) is not int or event.version != expected_version:
                raise ConflictError("event version conflict")
            event.title = title
            event.event_type = event_type
            event.start_at = start_at
            event.end_at = end_at
            event.updated_at = utc_now()
            event.version += 1
            if event.status == "draft":
                session.execute(
                    delete(EventEligibilityRuleRecord).where(
                        EventEligibilityRuleRecord.event_id == event_id
                    )
                )
                session.add_all(
                    EventEligibilityRuleRecord(event_id=event_id, qualification=value)
                    for value in sorted(rules)
                )
            else:
                self._add_event_audit(
                    session,
                    event_id=event_id,
                    actor_id=actor_id,
                    action="edited",
                    request_id=request_id,
                    details=details,
                )
            session.flush()
            return self._managed_event_in_session(session, event_id)

    def add_activity(
        self,
        actor_id: int,
        event_id: int,
        title: str,
        activity_type: str,
        start_at: datetime,
        end_at: datetime | None,
        request_id: str | None = None,
    ) -> int:
        title = _bounded_text(title, "activity title")
        require_choice(activity_type, ACTIVITY_TYPES, "activity type")
        _event_times(start_at, end_at)
        details = _operation_details(
            "activity_add",
            {
                "title": title,
                "activity_type": activity_type,
                "start_at": start_at,
                "end_at": end_at,
            },
        )
        with Session(self.engine) as session, session.begin():
            self._require_event_manager(session, actor_id)
            event = session.scalar(
                select(EventRecord).where(EventRecord.id == event_id).with_for_update()
            )
            if event is None or event.status == "cancelled":
                raise ConflictError("editable event required")
            if event.status == "published":
                if request_id is None:
                    raise ConflictError("published edit request id required")
                request_id = _request_id(request_id)
                existing = self._existing_event_audit(session, request_id)
                if existing is not None:
                    if (
                        existing.event_id == event_id
                        and existing.actor_person_id == actor_id
                        and existing.action == "edited"
                        and existing.details.get("operation") == details["operation"]
                        and existing.details.get("fingerprint")
                        == details["fingerprint"]
                    ):
                        return existing.details["target_id"]
                    raise ConflictError("event request id already used")
            position = (
                session.scalar(
                    select(func.max(ActivityRecord.position)).where(
                        ActivityRecord.event_id == event_id
                    )
                )
                or 0
            ) + 1
            activity = ActivityRecord(
                event_id=event_id,
                title=title,
                activity_type=activity_type,
                position=position,
                start_at=start_at,
                end_at=end_at,
                game_id=None,
            )
            session.add(activity)
            event.version += 1
            event.updated_at = utc_now()
            session.flush()
            if event.status == "published":
                self._add_event_audit(
                    session,
                    event_id=event_id,
                    actor_id=actor_id,
                    action="edited",
                    request_id=request_id,
                    details={**details, "target_id": activity.id},
                )
            return activity.id

    def _locked_activity(
        self, session: Session, event_id: int, activity_id: int
    ) -> ActivityRecord:
        activity = session.scalar(
            select(ActivityRecord)
            .where(
                ActivityRecord.id == activity_id,
                ActivityRecord.event_id == event_id,
            )
            .with_for_update()
        )
        if activity is None:
            raise ConflictError("activity does not belong to event")
        return activity

    def update_activity(
        self,
        actor_id: int,
        event_id: int,
        activity_id: int,
        title: str,
        activity_type: str,
        start_at: datetime,
        end_at: datetime | None,
        request_id: str,
    ) -> None:
        title = _bounded_text(title, "activity title")
        require_choice(activity_type, ACTIVITY_TYPES, "activity type")
        _event_times(start_at, end_at)
        request_id = _request_id(request_id)
        details = _operation_details(
            "activity_update",
            {
                "title": title,
                "activity_type": activity_type,
                "start_at": start_at,
                "end_at": end_at,
            },
            target_id=activity_id,
        )
        with Session(self.engine) as session, session.begin():
            self._require_event_manager(session, actor_id)
            event = session.scalar(
                select(EventRecord).where(EventRecord.id == event_id).with_for_update()
            )
            if event is None or event.status == "cancelled":
                raise ConflictError("editable event required")
            activity = self._locked_activity(session, event_id, activity_id)
            existing = self._existing_event_audit(session, request_id)
            if existing is not None:
                if (
                    existing.event_id == event_id
                    and existing.actor_person_id == actor_id
                    and existing.action == "edited"
                    and existing.details == details
                ):
                    return
                raise ConflictError("event request id already used")
            activity.title = title
            activity.activity_type = activity_type
            activity.start_at = start_at
            activity.end_at = end_at
            event.version += 1
            event.updated_at = utc_now()
            if event.status == "published":
                self._add_event_audit(
                    session,
                    event_id=event_id,
                    actor_id=actor_id,
                    action="edited",
                    request_id=request_id,
                    details=details,
                )

    def delete_activity(
        self,
        actor_id: int,
        event_id: int,
        activity_id: int,
        request_id: str | None = None,
    ) -> None:
        details = _operation_details("activity_delete", {}, target_id=activity_id)
        with Session(self.engine) as session, session.begin():
            self._require_event_manager(session, actor_id)
            event = session.scalar(
                select(EventRecord).where(EventRecord.id == event_id).with_for_update()
            )
            if event is None or event.status == "cancelled":
                raise ConflictError("editable event required")
            if event.status == "published":
                if request_id is None:
                    raise ConflictError("published edit request id required")
                request_id = _request_id(request_id)
                existing = self._existing_event_audit(session, request_id)
                if existing is not None:
                    if (
                        existing.event_id == event_id
                        and existing.actor_person_id == actor_id
                        and existing.action == "edited"
                        and existing.details == details
                    ):
                        return
                    raise ConflictError("event request id already used")
                self._add_event_audit(
                    session,
                    event_id=event_id,
                    actor_id=actor_id,
                    action="edited",
                    request_id=request_id,
                    details=details,
                )
            activity = self._locked_activity(session, event_id, activity_id)
            removed_position = activity.position
            session.delete(activity)
            session.flush()
            remaining = session.scalars(
                select(ActivityRecord)
                .where(
                    ActivityRecord.event_id == event_id,
                    ActivityRecord.position > removed_position,
                )
                .order_by(ActivityRecord.position, ActivityRecord.id)
                .with_for_update()
            ).all()
            for row in remaining:
                row.position = -row.id
            session.flush()
            for position, row in enumerate(remaining, removed_position):
                row.position = position
            event.version += 1
            event.updated_at = utc_now()

    def move_activity(
        self,
        actor_id: int,
        event_id: int,
        activity_id: int,
        direction: str,
        request_id: str | None = None,
    ) -> None:
        if direction not in {"up", "down"}:
            raise ConflictError("invalid activity direction")
        details = _operation_details(
            "activity_move", {"direction": direction}, target_id=activity_id
        )
        with Session(self.engine) as session, session.begin():
            self._require_event_manager(session, actor_id)
            event = session.scalar(
                select(EventRecord).where(EventRecord.id == event_id).with_for_update()
            )
            if event is None or event.status == "cancelled":
                raise ConflictError("editable event required")
            activity = self._locked_activity(session, event_id, activity_id)
            if event.status == "published":
                if request_id is None:
                    raise ConflictError("published edit request id required")
                request_id = _request_id(request_id)
                existing = self._existing_event_audit(session, request_id)
                if existing is not None:
                    if (
                        existing.event_id == event_id
                        and existing.actor_person_id == actor_id
                        and existing.action == "edited"
                        and existing.details == details
                    ):
                        return
                    raise ConflictError("event request id already used")
            target_position = activity.position + (-1 if direction == "up" else 1)
            target = session.scalar(
                select(ActivityRecord)
                .where(
                    ActivityRecord.event_id == event_id,
                    ActivityRecord.position == target_position,
                )
                .with_for_update()
            )
            if target is None:
                return
            if event.status == "published":
                self._add_event_audit(
                    session,
                    event_id=event_id,
                    actor_id=actor_id,
                    action="edited",
                    request_id=request_id,
                    details=details,
                )
            original = activity.position
            activity.position = -activity.id
            target.position = -target.id
            session.flush()
            activity.position = target_position
            target.position = original
            event.version += 1
            event.updated_at = utc_now()

    def cancel_event(self, actor_id: int, event_id: int, request_id: str) -> dict:
        request_id = _request_id(request_id)
        with Session(self.engine) as session, session.begin():
            self._require_event_manager(session, actor_id)
            event = session.scalar(
                select(EventRecord).where(EventRecord.id == event_id).with_for_update()
            )
            if event is None:
                raise ConflictError("event not found")
            existing = self._existing_event_audit(session, request_id)
            if existing is not None:
                if (
                    existing.event_id == event_id
                    and existing.actor_person_id == actor_id
                    and existing.action == "cancelled"
                ):
                    return self._managed_event_in_session(session, event_id)
                raise ConflictError("event request id already used")
            if event.status == "cancelled":
                return self._managed_event_in_session(session, event_id)
            if event.status != "published":
                raise ConflictError("published event required")
            event.status = "cancelled"
            event.version += 1
            event.updated_at = utc_now()
            self._add_event_audit(
                session,
                event_id=event_id,
                actor_id=actor_id,
                action="cancelled",
                request_id=request_id,
            )
            session.flush()
            return self._managed_event_in_session(session, event_id)

    def event_audits(self, event_id: int) -> tuple[dict, ...]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(EventAuditRecord)
                .where(EventAuditRecord.event_id == event_id)
                .order_by(EventAuditRecord.id)
            ).all()
            return tuple(
                {
                    "event_id": row.event_id,
                    "actor": row.actor_person_id,
                    "action": row.action,
                    "request_id": row.request_id,
                    "details": row.details,
                    "reason": row.reason,
                }
                for row in rows
            )

    def set_invitee_override(
        self,
        actor_id: int,
        event_id: int,
        person_id: int,
        action: str,
        participation_category: str,
        reason: str,
        request_id: str,
    ) -> None:
        if action not in {"include", "exclude"}:
            raise ConflictError("invalid override")
        if participation_category not in QUALIFICATIONS | {"other"}:
            raise ConflictError("invalid participation category")
        reason = require_reason(reason)
        request_id = _request_id(request_id)
        details = _operation_details(
            "override",
            {
                "person_id": person_id,
                "action": action,
                "participation_category": participation_category,
                "reason": reason,
            },
            target_id=person_id,
        )
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": self.EVENT_SNAPSHOT_LOCK_KEY},
            )
            self._require_event_manager(session, actor_id)
            event = session.scalar(
                select(EventRecord).where(EventRecord.id == event_id).with_for_update()
            )
            if event is None or event.status != "draft":
                raise ConflictError("draft event required")
            if session.get(PersonRecord, person_id) is None:
                raise ConflictError("person not found")
            existing_audit = self._existing_event_audit(session, request_id)
            audit_action = (
                "invitee_included" if action == "include" else "invitee_excluded"
            )
            if existing_audit is not None:
                if (
                    existing_audit.event_id == event_id
                    and existing_audit.actor_person_id == actor_id
                    and existing_audit.action == audit_action
                    and existing_audit.details == details
                    and existing_audit.reason == reason
                ):
                    return
                raise ConflictError("event request id already used")
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
            self._add_event_audit(
                session,
                event_id=event_id,
                actor_id=actor_id,
                action=audit_action,
                request_id=request_id,
                details=details,
                reason=reason,
            )

    def publish_event(
        self, actor_id: int, event_id: int, request_id: str
    ) -> list[Invitee]:
        request_id = _request_id(request_id)
        now = utc_now()
        with Session(self.engine) as session, session.begin():
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": self.EVENT_SNAPSHOT_LOCK_KEY},
            )
            self._require_event_manager(session, actor_id)
            event = session.scalar(
                select(EventRecord).where(EventRecord.id == event_id).with_for_update()
            )
            if event is None:
                raise ConflictError("event not found")
            rules = set(
                session.scalars(
                    select(EventEligibilityRuleRecord.qualification).where(
                        EventEligibilityRuleRecord.event_id == event_id
                    )
                )
            )
            details = _operation_details("publish", {"eligibility": sorted(rules)})
            existing_audit = self._existing_event_audit(session, request_id)
            if existing_audit is not None:
                if (
                    existing_audit.event_id == event_id
                    and existing_audit.actor_person_id == actor_id
                    and existing_audit.action == "published"
                    and existing_audit.details == details
                ):
                    return self._event_invitees(session, event_id)
                raise ConflictError("event request id already used")
            if event.status == "published":
                return self._event_invitees(session, event_id)
            if event.status != "draft":
                raise ConflictError("draft event required")
            if not rules:
                raise ConflictError("event eligibility cannot be empty")
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
                    details=details,
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
