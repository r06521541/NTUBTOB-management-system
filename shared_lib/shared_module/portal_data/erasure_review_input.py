"""Strict internal import of an already authorized human review, never a public API.

The trusted caller must authenticate the reviewer and protect the private payload.
This codec establishes shape/freshness, NOT authorship or completeness of review.
Keep the caller's clean transaction open through capture_person_snapshot; that
capture independently checks ownership and the complete required inventory. No
row is changed here, and no guessed replacement is generated on stale input.
"""

import hmac
import json
import re
from uuid import UUID

from .erasure_fulfillment import _connection
from .erasure_person_fulfillment import (
    CONTENT_FIELDS,
    _capture_roots,
    _lock,
    seal_reviewed_person_disposition,
)

# Resource limits only, not processing or retention promises.
MAX_BYTES = 1024 * 1024
MAX_ROWS = 1000
_ATTRIBUTION = {
    "access_audit": ("actor_person_id", "target_person_id", "auth_identity_id"),
    "event_audit": ("actor_person_id",),
    "guest_qualification_audits": ("actor_person_id",),
    "events": ("created_by_person_id",),
    "identity_review_messages": ("sender_person_id", "body_redacted"),
    "identity_review_threads": ("auth_identity_id",),
    "mobile_notification_publish_audits": ("actor_person_id", "audience_reference_id"),
    "event_notification_publish_audits": ("actor_person_id",),
    "person_qualifications": ("granted_by_person_id",),
    "event_invitee_overrides": ("actor_person_id",),
    "event_invitees": ("actor_person_id",),
    "event_managers": ("assigned_by_person_id",),
}
_ROW_KEYS = {
    "table",
    "row_id",
    "old_digest",
    "action",
    "patch",
    "reviewed_fields",
    "decision",
}


class ReviewInputRejected(ValueError):
    """Invalid or stale private review, without supplied values."""


class ReviewInputUnavailable(RuntimeError):
    """Storage/transaction check unavailable, not permission to repeat mutation."""


def _reject():
    raise ReviewInputRejected("review_input_rejected") from None


def _pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            _reject()
        result[key] = value
    return result


def _identifier(value):
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        _reject()


def _parse(payload, person_id, generation):
    _identifier(person_id)
    try:
        if type(generation) is not str or str(UUID(generation)) != generation:
            _reject()
        if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES:
            _reject()
        data = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=lambda _: _reject(),
        )
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _reject()
    if (
        type(data) is not dict
        or set(data) != {"version", "person_id", "generation", "dispositions"}
        or type(data["version"]) is not int
        or data["version"] != 1
        or type(data["person_id"]) is not int
        or data["person_id"] != person_id
        or data["generation"] != generation
        or type(data["dispositions"]) is not list
        or len(data["dispositions"]) > MAX_ROWS
    ):
        _reject()
    seen = set()
    for row in data["dispositions"]:
        if type(row) is not dict or set(row) != _ROW_KEYS:
            _reject()
        table = row["table"]
        if type(table) is not str or table not in CONTENT_FIELDS:
            _reject()
        _identifier(row["row_id"])
        identity = (table, row["row_id"])
        if identity in seen:
            _reject()
        seen.add(identity)
        if (
            type(row["old_digest"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", row["old_digest"]) is None
            or type(row["action"]) is not str
            or row["action"] not in {"retain", "update", "delete"}
            or type(row["patch"]) is not dict
            or set(row["patch"])
            - set(CONTENT_FIELDS[table] + _ATTRIBUTION.get(table, ()))
            or type(row["reviewed_fields"]) is not list
            or row["reviewed_fields"] != list(CONTENT_FIELDS[table])
            or row["decision"]
            != (
                "own_content_delete"
                if row["action"] == "delete"
                else "no_target_content_after_disposition"
            )
            or (row["action"] == "update") != bool(row["patch"])
            or (
                row["action"] == "delete" and table in {"games", "events", "activities"}
            )
        ):
            _reject()
        if len(json.dumps(row["patch"], ensure_ascii=True, allow_nan=False)) > 65536:
            _reject()
    return data["dispositions"]


def import_person_review(session, *, payload, person_id, generation):
    """Return reviewed DTOs under the same caller-owned locked transaction.

    Duplicate keys (including nested patches), unknown fields and stale row hashes
    reject the entire import. The caller cannot use an importer success as an
    ownership check; capture and execution retain their own exact-scope checks.
    """
    try:
        rows = _parse(payload, person_id, generation)
    except ReviewInputRejected:
        raise
    except (ValueError, TypeError, RecursionError):
        _reject()
    try:
        connection = _connection(session)
        _lock(connection)
        person, _ = _capture_roots(connection, person_id)
        if person[0] != generation:
            _reject()
        result = []
        for row in rows:
            sealed = seal_reviewed_person_disposition(
                connection,
                table=row["table"],
                row_id=row["row_id"],
                action=row["action"],
                patch=row["patch"],
                reviewed_fields=tuple(row["reviewed_fields"]),
                decision=row["decision"],
            )
            if not hmac.compare_digest(sealed.old_digest, row["old_digest"]):
                _reject()
            result.append(sealed)
        return tuple(result)
    except ReviewInputRejected:
        raise
    except Exception:
        raise ReviewInputUnavailable("review_input_unavailable") from None
