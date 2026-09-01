from __future__ import annotations

from datetime import datetime, timezone

MAX_POSTGRESQL_BIGINT = 9_223_372_036_854_775_807
EVENT_TYPES = frozenset({"game", "meal", "trip", "practice", "social", "other"})
EVENT_STATUSES = frozenset({"published", "cancelled"})
ACTIVITY_TYPES = frozenset(
    {"game", "meal", "transport", "lodging", "gathering", "other"}
)
EVENT_ATTENDANCE_REPLIES = frozenset({"attending", "not_attending", "maybe"})
PARTICIPATION_CATEGORIES = frozenset(
    {"team_player", "guest_player", "affiliate", "staff", "other"}
)


class EventReadContractError(ValueError):
    """Stored or transported Event data violates the public read contract."""


def parse_event_key(value: object) -> int:
    """Decode one canonical positive PostgreSQL bigint Event key."""
    if not isinstance(value, str) or not value.startswith("event_"):
        raise EventReadContractError("event_id is malformed")
    suffix = value[6:]
    if (
        not suffix
        or len(suffix) > 19
        or not suffix.isascii()
        or not suffix.isdecimal()
        or suffix.startswith("0")
    ):
        raise EventReadContractError("event_id is malformed")
    parsed = int(suffix)
    if parsed > MAX_POSTGRESQL_BIGINT:
        raise EventReadContractError("event_id is malformed")
    return parsed


def project_public_event(event: dict) -> dict:
    """Return the privacy-bounded Event/Activity projection shared by clients."""

    if not isinstance(event, dict):
        raise EventReadContractError("stored event is malformed")

    def positive_opaque(prefix: str, value: object) -> str:
        if type(value) is not int or not 1 <= value <= MAX_POSTGRESQL_BIGINT:
            raise EventReadContractError(f"{prefix}_id is malformed")
        return f"{prefix}_{value}"

    def signed_game_opaque(value: object) -> str:
        if (
            type(value) is not int
            or value == 0
            or not -MAX_POSTGRESQL_BIGINT - 1 <= value <= MAX_POSTGRESQL_BIGINT
        ):
            raise EventReadContractError("game_id is malformed")
        return f"game_{value}"

    def utc(value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise EventReadContractError("stored event timestamp is malformed")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def bounded_text(value: object, field: str) -> str:
        if not isinstance(value, str) or not 1 <= len(value) <= 200:
            raise EventReadContractError(f"stored {field} is malformed")
        return value

    def attendance(value: object, field: str) -> dict | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise EventReadContractError(f"stored {field} attendance is malformed")
        own_reply = value.get("own_reply")
        counts = value.get("counts")
        if own_reply is not None and own_reply not in EVENT_ATTENDANCE_REPLIES:
            raise EventReadContractError(f"stored {field} attendance is malformed")
        expected = EVENT_ATTENDANCE_REPLIES | {"unanswered"}
        if (
            not isinstance(counts, dict)
            or set(counts) != expected
            or any(type(counts[key]) is not int or counts[key] < 0 for key in expected)
        ):
            raise EventReadContractError(f"stored {field} attendance is malformed")
        return {
            "own_reply": own_reply,
            "counts": {key: counts[key] for key in sorted(expected)},
        }

    event_type = event.get("type")
    if event_type not in EVENT_TYPES:
        raise EventReadContractError("stored event type is malformed")
    status = event.get("status")
    if status not in EVENT_STATUSES:
        raise EventReadContractError("stored event status is malformed")
    participation_category = event.get("participation_category")
    if participation_category not in PARTICIPATION_CATEGORIES:
        raise EventReadContractError("stored participation category is malformed")

    source_activities = event.get("activities")
    if not isinstance(source_activities, (list, tuple)):
        raise EventReadContractError("stored activities are malformed")
    source_attendance = event.get("attendance")
    if source_attendance is None:
        event_attendance = None
        activity_attendance = {}
    elif not isinstance(source_attendance, dict):
        raise EventReadContractError("stored event attendance is malformed")
    else:
        activity_attendance = source_attendance.get("activities")
        if not isinstance(activity_attendance, dict):
            raise EventReadContractError("stored activity attendance is malformed")
        event_attendance = attendance(source_attendance, "event")

    activities = []
    for activity in source_activities:
        if not isinstance(activity, dict):
            raise EventReadContractError("stored activity is malformed")
        if activity.get("start_at") is None:
            raise EventReadContractError("stored activity timestamp is malformed")
        linked_game_id = activity.get("linked_game_id")
        activity_type = activity.get("type")
        if activity_type not in ACTIVITY_TYPES:
            raise EventReadContractError("stored activity type is malformed")
        position = activity.get("position")
        if type(position) is not int:
            raise EventReadContractError("stored activity position is malformed")
        activity_id = activity.get("id")
        projected_activity_attendance = (
            None
            if linked_game_id is not None
            else (
                attendance(activity_attendance.get(activity_id), "activity")
                if source_attendance is not None
                else None
            )
        )
        if (
            linked_game_id is not None
            and activity_attendance.get(activity_id) is not None
        ):
            raise EventReadContractError(
                "linked Game attendance must not be duplicated"
            )
        activities.append(
            {
                "id": positive_opaque("activity", activity_id),
                "title": bounded_text(activity.get("title"), "activity title"),
                "type": activity_type,
                "position": position,
                "start_at": utc(activity.get("start_at")),
                "end_at": utc(activity.get("end_at")),
                "linked_game_id": (
                    signed_game_opaque(linked_game_id)
                    if linked_game_id is not None
                    else None
                ),
                "attendance": projected_activity_attendance,
            }
        )
    if event.get("start_at") is None:
        raise EventReadContractError("stored event timestamp is malformed")
    return {
        "id": positive_opaque("event", event.get("id")),
        "title": bounded_text(event.get("title"), "event title"),
        "type": event_type,
        "status": status,
        "participation_category": participation_category,
        "start_at": utc(event.get("start_at")),
        "end_at": utc(event.get("end_at")),
        "attendance": event_attendance,
        "activities": activities,
    }
