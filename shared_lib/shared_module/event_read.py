from __future__ import annotations

from datetime import datetime, timezone

MAX_POSTGRESQL_BIGINT = 9_223_372_036_854_775_807
EVENT_TYPES = frozenset({"game", "meal", "trip", "practice", "social", "other"})
EVENT_STATUSES = frozenset({"published", "cancelled"})
ACTIVITY_TYPES = frozenset(
    {"game", "meal", "transport", "lodging", "gathering", "other"}
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

    event_type = event.get("type")
    if event_type not in EVENT_TYPES:
        raise EventReadContractError("stored event type is malformed")
    status = event.get("status")
    if status not in EVENT_STATUSES:
        raise EventReadContractError("stored event status is malformed")

    source_activities = event.get("activities")
    if not isinstance(source_activities, (list, tuple)):
        raise EventReadContractError("stored activities are malformed")
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
        activities.append(
            {
                "id": positive_opaque("activity", activity.get("id")),
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
            }
        )
    if event.get("start_at") is None:
        raise EventReadContractError("stored event timestamp is malformed")
    return {
        "id": positive_opaque("event", event.get("id")),
        "title": bounded_text(event.get("title"), "event title"),
        "type": event_type,
        "status": status,
        "start_at": utc(event.get("start_at")),
        "end_at": utc(event.get("end_at")),
        "activities": activities,
    }
