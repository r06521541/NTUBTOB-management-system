"""Approved remote staging migration/fixture operation; dry-run by default."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

try:
    from .mobile_staging_contract import (
        FORWARD_REVISIONS,
        REVISION,
        StagingContractError,
        load_approval,
        validate_database_identity,
    )
    from .mobile_staging_seed import (
        ANCHOR,
        FIXTURE_REPLY_AT,
        StagingSeedError,
        _validate_subject,
        inspect_attendance_repair,
        repair_attendance_fixture,
        seed,
    )
    from .setup_portal_data_legacy import LEGACY_FIXTURE_SQL
except ImportError:  # pragma: no cover
    from mobile_staging_contract import (
        FORWARD_REVISIONS,
        REVISION,
        StagingContractError,
        load_approval,
        validate_database_identity,
    )
    from mobile_staging_seed import (
        ANCHOR,
        FIXTURE_REPLY_AT,
        StagingSeedError,
        _validate_subject,
        inspect_attendance_repair,
        repair_attendance_fixture,
        seed,
    )
    from setup_portal_data_legacy import LEGACY_FIXTURE_SQL

BASE_REVISION = "0001_legacy_baseline"
LEGACY_TABLES = {
    "attendance_reply_types",
    "ballparks",
    "cancellations",
    "discord_webhooks",
    "game_attendance_replies",
    "games",
    "line_groups",
    "line_notify_tokens",
    "line_users",
    "members",
}
PORTAL_TABLES = {
    "access_audit",
    "activities",
    "activity_attendance_replies",
    "auth_identities",
    "event_attendance_replies",
    "event_audit",
    "event_eligibility_rules",
    "event_invitee_overrides",
    "event_invitees",
    "event_managers",
    "events",
    "identity_review_messages",
    "identity_review_threads",
    "people",
    "person_qualifications",
}
MOBILE_TABLES = {
    "mobile_auth_exchanges",
    "mobile_idempotency_records",
    "mobile_refresh_attempts",
    "mobile_refresh_tokens",
    "mobile_sessions",
}
BASE_EXPECTED_TABLES = (
    LEGACY_TABLES | PORTAL_TABLES | MOBILE_TABLES | {"alembic_version"}
)
AUTH_REVISION, BROKER_REVISION = FORWARD_REVISIONS
BROKER_TABLES = frozenset({"staging_broker_operations"})
NOTIFICATION_TABLES = frozenset(
    {
        "mobile_notifications",
        "mobile_notification_recipients",
        "mobile_notification_publish_audits",
        "mobile_notification_deliveries",
        "mobile_device_registrations",
    }
)
EXPECTED_TABLES = BASE_EXPECTED_TABLES | BROKER_TABLES | NOTIFICATION_TABLES
REVISION_TABLES = {
    AUTH_REVISION: BASE_EXPECTED_TABLES,
    BROKER_REVISION: BASE_EXPECTED_TABLES | BROKER_TABLES,
    REVISION: EXPECTED_TABLES,
}
LEGACY_IDS = {
    "attendance_reply_types": (9101, 9102, 9103),
    "ballparks": (9301,),
    "game_attendance_replies": (9601, 9602, 9603, 9604),
    "games": (9401, 9402),
    "line_users": (9501, 9502, 9503),
    "members": (9201, 9202),
    "people": (1,),
    "person_qualifications": (1,),
    "access_audit": (1,),
}
MOBILE_FIXTURE_IDS = (-112003, -112002, -112001)
OFFICER_PERSON_ID = -112001
OFFICER_IDENTITY_ID = -112001
OFFICER_AUDIT_IDS = {"grant": -119001, "restore": -119002}
OFFICER_REQUEST_IDS = {
    "grant": "task-119-fictional-officer-grant",
    "restore": "task-119-fictional-officer-restore",
}
OFFICER_AUDITS = {
    "grant": {
        "before": {"access_level": "basic", "fixture": "TASK-112/TASK-118"},
        "after": {"access_level": "officer", "fixture": "TASK-119"},
        "reason": "TASK-119 fictional Officer grant",
    },
    "restore": {
        "before": {"access_level": "officer", "fixture": "TASK-119"},
        "after": {"access_level": "basic", "fixture": "TASK-112/TASK-118"},
        "reason": "TASK-119 fictional Officer restore",
    },
}
LIFECYCLE_FIXTURE = "TASK-126"
LIFECYCLE_REQUEST_PREFIX = "task-126-fixture-lifecycle"
LIFECYCLE_REASON_PREFIX = "TASK-126 fictional fixture lifecycle"
RUNTIME_RESIDUE_ROWS = (
    (
        3,
        -112001,
        None,
        None,
        -112001,
        5,
        datetime(2026, 8, 19, 16, 33, 2, 723958, tzinfo=timezone.utc),
    ),
    (
        4,
        -112001,
        None,
        None,
        -112001,
        1,
        datetime(2026, 8, 19, 16, 36, 23, 695486, tzinfo=timezone.utc),
    ),
)
CANONICAL_FIXTURE_REPLY_ROWS = (
    (-112003, -112002, None, None, -112003, 5, FIXTURE_REPLY_AT),
    (-112002, -112001, None, None, -112002, 2, FIXTURE_REPLY_AT),
    (-112001, -112001, None, None, -112001, 1, FIXTURE_REPLY_AT),
)
CANONICAL_ATTENDANCE = {
    row[0]: {
        "game_id": row[1],
        "user_id": row[2],
        "member_id": row[3],
        "person_id": row[4],
        "reply": row[5],
    }
    for row in CANONICAL_FIXTURE_REPLY_ROWS
}
AUDIT_FIELDS = (
    "id",
    "action",
    "actor_person_id",
    "target_person_id",
    "auth_identity_id",
    "before_state",
    "after_state",
    "reason",
    "request_id",
)


def _legacy_audit(transition: str) -> dict:
    expected = OFFICER_AUDITS[transition]
    return {
        "id": OFFICER_AUDIT_IDS[transition],
        "action": "access_changed",
        "actor_person_id": None,
        "target_person_id": OFFICER_PERSON_ID,
        "auth_identity_id": OFFICER_IDENTITY_ID,
        "before_state": expected["before"],
        "after_state": expected["after"],
        "reason": expected["reason"],
        "request_id": OFFICER_REQUEST_IDS[transition],
    }


def _lifecycle_audit(version: int, transition: str, audit_id=None) -> dict:
    before = "basic" if transition == "grant" else "officer"
    after = "officer" if transition == "grant" else "basic"
    return {
        "id": audit_id,
        "action": "access_changed",
        "actor_person_id": None,
        "target_person_id": OFFICER_PERSON_ID,
        "auth_identity_id": OFFICER_IDENTITY_ID,
        "before_state": {
            "access_level": before,
            "fixture": LIFECYCLE_FIXTURE,
            "version": version,
        },
        "after_state": {
            "access_level": after,
            "fixture": LIFECYCLE_FIXTURE,
            "version": version + 1,
        },
        "reason": f"{LIFECYCLE_REASON_PREFIX} {transition}",
        "request_id": f"{LIFECYCLE_REQUEST_PREFIX}-v{version}-{transition}",
    }


def _audit_shape(row) -> dict:
    values = dict(row)
    return {field: values.get(field) for field in AUDIT_FIELDS}


def _classify_role_lifecycle(person: dict, audits: Sequence[dict]) -> str:
    """Validate the complete append-only fixture role chain."""
    expected_role = "basic"
    expected_version = 1
    position = 0
    rows = [_audit_shape(row) for row in audits]
    for transition in ("grant", "restore"):
        if position >= len(rows):
            break
        if rows[position] != _legacy_audit(transition):
            raise StagingContractError("Officer fixture lifecycle audit is drifted")
        expected_role = "officer" if transition == "grant" else "basic"
        expected_version += 1
        position += 1

    while position < len(rows):
        transition = "grant" if expected_role == "basic" else "restore"
        expected = _lifecycle_audit(
            expected_version, transition, rows[position].get("id")
        )
        if rows[position] != expected:
            raise StagingContractError("Officer fixture lifecycle audit is drifted")
        expected_role = "officer" if transition == "grant" else "basic"
        expected_version += 1
        position += 1

    if (
        person.get("portal_access_level") != expected_role
        or person.get("version") != expected_version
    ):
        raise StagingContractError("Officer fixture audit or version is drifted")
    if expected_role == "officer":
        return "granted"
    return "baseline" if expected_version == 1 else "restored"


def _fixture_audits(connection) -> list[dict]:
    return list(
        connection.execute(
            text(
                "SELECT id, action, actor_person_id, target_person_id, "
                "auth_identity_id, before_state, after_state, reason, request_id, "
                "created_at "
                "FROM ntubtob.access_audit WHERE action='access_changed' AND "
                "(target_person_id=:person OR auth_identity_id=:identity) ORDER BY "
                "CASE id WHEN -119001 THEN 0 WHEN -119002 THEN 1 ELSE 2 END, id"
            ),
            {"person": OFFICER_PERSON_ID, "identity": OFFICER_IDENTITY_ID},
        ).mappings()
    )


def _legacy_fixture_audit(connection) -> bool:
    row = (
        connection.execute(
            text(
                "SELECT id, action, actor_person_id, target_person_id, "
                "auth_identity_id, before_state, after_state, reason, request_id "
                "FROM ntubtob.access_audit WHERE id=1"
            )
        )
        .mappings()
        .one_or_none()
    )
    return row == {
        "id": 1,
        "action": "member_backfilled",
        "actor_person_id": None,
        "target_person_id": 1,
        "auth_identity_id": None,
        "before_state": {"member_id": 9201, "person_id": None},
        "after_state": {"member_id": 9201, "person_id": 1},
        "reason": "Phase C attendance compatibility backfill",
        "request_id": "phase-c-attendance-member-9201",
    }


def _google_recovery_fingerprint(connection) -> tuple:
    """Accept only one complete Google recovery graph for the fictional tester."""
    canonical_identities = list(
        connection.execute(
            text(
                "SELECT id, provider, provider_subject, person_id, status, "
                "created_at, updated_at FROM ntubtob.auth_identities "
                "WHERE id = ANY(:fixture_ids) ORDER BY id"
            ),
            {"fixture_ids": list(MOBILE_FIXTURE_IDS)},
        ).mappings()
    )
    if (
        len(canonical_identities) != 3
        or any(
            row["provider"] != "line"
            or row["person_id"] != row["id"]
            or row["status"] != "linked"
            or row["created_at"] != ANCHOR
            or row["updated_at"] != ANCHOR
            for row in canonical_identities
        )
        or canonical_identities[0]["provider_subject"] != "task112-fictional-teammate-b"
        or canonical_identities[1]["provider_subject"] != "task112-fictional-teammate-a"
        or not isinstance(canonical_identities[2]["provider_subject"], str)
        or not 8 <= len(canonical_identities[2]["provider_subject"]) <= 255
        or canonical_identities[2]["provider_subject"]
        in {"task112-fictional-teammate-a", "task112-fictional-teammate-b"}
    ):
        raise StagingContractError("Canonical fictional identities are drifted")
    identities = list(
        connection.execute(
            text(
                "SELECT * FROM ntubtob.auth_identities "
                "WHERE id <> ALL(:fixture_ids) ORDER BY id"
            ),
            {"fixture_ids": list(MOBILE_FIXTURE_IDS)},
        ).mappings()
    )
    lifecycle_audits = list(
        connection.execute(
            text(
                "SELECT * FROM ntubtob.access_audit "
                "WHERE action IN ('identity_pending', 'identity_linked') "
                "ORDER BY created_at, id"
            )
        ).mappings()
    )
    threads = list(
        connection.execute(
            text("SELECT * FROM ntubtob.identity_review_threads ORDER BY id")
        ).mappings()
    )
    messages = list(
        connection.execute(
            text("SELECT * FROM ntubtob.identity_review_messages ORDER BY id")
        ).mappings()
    )
    role_audits = _fixture_audits(connection)
    expected_audit_ids = {
        1,
        *(int(row["id"]) for row in role_audits),
        *(int(row["id"]) for row in lifecycle_audits),
    }
    if set(_ids(connection, "access_audit")) != expected_audit_ids:
        raise StagingContractError("Google recovery audit graph is drifted")

    if not identities:
        if lifecycle_audits or threads or messages:
            raise StagingContractError("Google recovery graph is partial")
        return ()
    if len(identities) != 1 or len(lifecycle_audits) != 2 or len(threads) != 1:
        raise StagingContractError("Google recovery graph is partial or duplicated")
    if messages:
        raise StagingContractError("Google recovery graph contains unknown messages")

    identity = identities[0]
    pending, linked = lifecycle_audits
    thread = threads[0]
    subject = identity["provider_subject"]
    pending_request = (
        "identity-pending-"
        + hashlib.sha256(f"google:{subject}".encode("utf-8")).hexdigest()[:32]
    )
    linked_request = linked["request_id"]
    if (
        identity["provider"] != "google"
        or identity["person_id"] != OFFICER_PERSON_ID
        or identity["status"] != "linked"
        or not isinstance(subject, str)
        or not 8 <= len(subject) <= 255
        or identity["created_at"] is None
        or identity["updated_at"] is None
        or identity["created_at"] > identity["updated_at"]
        or pending["action"] != "identity_pending"
        or pending["actor_person_id"] is not None
        or pending["target_person_id"] is not None
        or pending["auth_identity_id"] != identity["id"]
        or pending["before_state"] is not None
        or pending["after_state"] != {"status": "pending"}
        or pending["reason"] != "Google identity awaiting self-link confirmation"
        or pending["request_id"] != pending_request
        or pending["created_at"] != identity["created_at"]
        or linked["action"] != "identity_linked"
        or linked["actor_person_id"] != OFFICER_PERSON_ID
        or linked["target_person_id"] != OFFICER_PERSON_ID
        or linked["auth_identity_id"] != identity["id"]
        or linked["before_state"] != {"status": "pending"}
        or linked["after_state"]
        != {
            "status": "linked",
            "source_provider": "line",
            "target_provider": "google",
            "outcome": "recovery_link",
        }
        or linked["reason"] != "Self-service cross-provider identity link"
        or not isinstance(linked_request, str)
        or re.fullmatch(r"identity-self-link-[0-9a-f]{40}", linked_request) is None
        or linked["created_at"] != identity["updated_at"]
        or pending["created_at"] > linked["created_at"]
        or thread["auth_identity_id"] != identity["id"]
        or thread["status"] != "closed"
        or thread["last_applicant_message_at"] is not None
        or thread["last_activity_at"] != linked["created_at"]
        or thread["closed_at"] != linked["created_at"]
        or thread["redacted_at"] is not None
        or thread["created_at"] != pending["created_at"]
        or thread["updated_at"] != linked["created_at"]
    ):
        raise StagingContractError("Google recovery graph is drifted")
    return (
        tuple(identity.values()),
        tuple(tuple(row.values()) for row in lifecycle_audits),
        tuple(thread.values()),
    )


def _officer_subject(value: str) -> str:
    try:
        return _validate_subject(value)
    except StagingSeedError:
        raise StagingContractError("Private tester input is invalid") from None


def _mobile_history_is_exact(connection) -> bool:
    if all(
        connection.scalar(text(f"SELECT count(*) FROM ntubtob.{table}")) == 0
        for table in MOBILE_TABLES
    ):
        return True
    checks = (
        (
            "mobile_sessions",
            "SELECT count(*) FROM ntubtob.mobile_sessions "
            "s JOIN ntubtob.auth_identities i ON i.id=s.auth_identity_id "
            "WHERE s.person_id=-112001 AND i.person_id=s.person_id "
            "AND i.status='linked' AND i.provider IN ('line', 'google')",
        ),
        (
            "mobile_refresh_tokens",
            "SELECT count(*) FROM ntubtob.mobile_refresh_tokens t "
            "JOIN ntubtob.mobile_sessions s ON s.id=t.session_id "
            "JOIN ntubtob.auth_identities i ON i.id=s.auth_identity_id "
            "WHERE s.person_id=-112001 AND i.person_id=s.person_id "
            "AND i.status='linked' AND i.provider IN ('line', 'google')",
        ),
        (
            "mobile_refresh_attempts",
            "SELECT count(*) FROM ntubtob.mobile_refresh_attempts a "
            "JOIN ntubtob.mobile_sessions s ON s.id=a.session_id "
            "JOIN ntubtob.auth_identities i ON i.id=s.auth_identity_id "
            "WHERE s.person_id=-112001 AND i.person_id=s.person_id "
            "AND i.status='linked' AND i.provider IN ('line', 'google')",
        ),
        (
            "mobile_auth_exchanges",
            "SELECT count(*) FROM ntubtob.mobile_auth_exchanges e "
            "JOIN ntubtob.mobile_sessions s ON s.id=e.session_id "
            "JOIN ntubtob.auth_identities i ON i.id=s.auth_identity_id "
            "WHERE e.provider IN ('line', 'google') AND s.person_id=-112001 "
            "AND i.person_id=s.person_id AND i.status='linked' "
            "AND i.provider IN ('line', 'google')",
        ),
        (
            "mobile_idempotency_records",
            "SELECT count(*) FROM ntubtob.mobile_idempotency_records i "
            "JOIN ntubtob.mobile_sessions s ON s.id=i.session_id "
            "JOIN ntubtob.auth_identities a ON a.id=s.auth_identity_id "
            "WHERE i.person_id=-112001 AND s.person_id=i.person_id "
            "AND a.person_id=s.person_id AND a.status='linked' "
            "AND a.provider IN ('line', 'google')",
        ),
    )
    for table, owned_query in checks:
        total = connection.scalar(text(f"SELECT count(*) FROM ntubtob.{table}"))
        if connection.scalar(text(owned_query)) != total:
            return False
    google_exchanges = connection.scalar(
        text(
            "SELECT count(*) FROM ntubtob.mobile_auth_exchanges WHERE provider='google'"
        )
    )
    if (
        google_exchanges
        and connection.scalar(
            text(
                "SELECT count(*) FROM ntubtob.auth_identities WHERE provider='google' "
                "AND person_id=-112001 AND status='linked'"
            )
        )
        != 1
    ):
        return False
    return True


def _runtime_residue_is_exact(connection) -> bool:
    rows = connection.execute(
        text(
            "SELECT id, game_id, user_id, member_id, person_id, reply, updated_at "
            "FROM ntubtob.game_attendance_replies "
            "WHERE id = ANY(:canonical_ids) OR person_id = ANY(:fixture_ids) "
            "OR game_id = ANY(:fixture_ids) ORDER BY id"
        ),
        {
            "canonical_ids": list(CANONICAL_ATTENDANCE),
            "fixture_ids": list(MOBILE_FIXTURE_IDS),
        },
    ).all()
    return [tuple(row) for row in rows] == list(
        CANONICAL_FIXTURE_REPLY_ROWS + RUNTIME_RESIDUE_ROWS
    )


def _attendance_lifecycle_state(connection) -> bool:
    """Return whether known fixture-owned attendance requires reconstruction."""
    rows = list(
        connection.execute(
            text(
                "SELECT id, game_id, user_id, member_id, person_id, reply "
                "FROM ntubtob.game_attendance_replies "
                "WHERE id = ANY(:canonical_ids) OR person_id = ANY(:fixture_ids) "
                "OR game_id = ANY(:fixture_ids) ORDER BY id"
            ),
            {
                "canonical_ids": list(CANONICAL_ATTENDANCE),
                "fixture_ids": list(MOBILE_FIXTURE_IDS),
            },
        ).mappings()
    )
    seen = set()
    reset_required = False
    for row in rows:
        row = dict(row)
        canonical = CANONICAL_ATTENDANCE.get(row["id"])
        if canonical is not None:
            seen.add(row["id"])
            ownership = {
                key: row[key]
                for key in ("game_id", "user_id", "member_id", "person_id")
            }
            expected_ownership = {
                key: canonical[key]
                for key in ("game_id", "user_id", "member_id", "person_id")
            }
            if ownership != expected_ownership:
                raise StagingContractError(
                    "Fixture attendance canonical ID collision is drifted"
                )
            reset_required = reset_required or row["reply"] != canonical["reply"]
            continue
        if (
            row["person_id"] not in MOBILE_FIXTURE_IDS
            or row["game_id"] not in MOBILE_FIXTURE_IDS
            or row["user_id"] is not None
            or row["member_id"] is not None
            or row["reply"] not in {1, 2, 3, 4, 5}
        ):
            raise StagingContractError("Fixture attendance ownership is drifted")
        reset_required = True
    return reset_required or seen != set(CANONICAL_ATTENDANCE)


def _attendance_is_canonical(connection) -> bool:
    no_noncanonical = connection.scalar(
        text(
            "SELECT NOT EXISTS (SELECT 1 "
            "FROM ntubtob.game_attendance_replies WHERE "
            "(person_id = ANY(:fixture_ids) OR game_id = ANY(:fixture_ids) "
            "OR id = ANY(:canonical_ids)) AND NOT (id = ANY(:canonical_ids)))"
        ),
        {
            "fixture_ids": list(MOBILE_FIXTURE_IDS),
            "canonical_ids": list(CANONICAL_ATTENDANCE),
        },
    )
    if not no_noncanonical:
        return False
    for row_id, expected in CANONICAL_ATTENDANCE.items():
        if not connection.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM ntubtob.game_attendance_replies "
                "WHERE id=:id AND game_id=:game_id AND user_id IS NULL "
                "AND member_id IS NULL AND person_id=:person_id AND reply=:reply)"
            ),
            {
                "id": row_id,
                "game_id": expected["game_id"],
                "person_id": expected["person_id"],
                "reply": expected["reply"],
            },
        ):
            return False
    return True


def _officer_fixture_state(
    connection,
    private_subject: str,
    allow_runtime_residue: bool = False,
    allow_attendance_reset: bool = False,
) -> str:
    """Classify only the exact append-only TASK-119 fixture states."""
    schema_exists = connection.scalar(
        text("SELECT to_regnamespace('ntubtob') IS NOT NULL")
    )
    if not schema_exists:
        raise StagingContractError("Officer fixture is not ready; do not retry")
    tables = tuple(
        connection.scalars(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='ntubtob' ORDER BY table_name"
            )
        )
    )
    revisions = tuple(
        connection.scalars(text("SELECT version_num FROM ntubtob.alembic_version"))
    )
    expected_revision = REVISION
    expected_tables = EXPECTED_TABLES
    if set(tables) != expected_tables or revisions != (expected_revision,):
        raise StagingContractError("Officer fixture is not ready; do not retry")

    expected = dict(LEGACY_IDS)
    expected["attendance_reply_types"] = (1, 2, 3, 4, 5) + LEGACY_IDS[
        "attendance_reply_types"
    ]
    expected["games"] = MOBILE_FIXTURE_IDS + LEGACY_IDS["games"]
    expected["people"] = MOBILE_FIXTURE_IDS + LEGACY_IDS["people"]
    expected["person_qualifications"] = MOBILE_FIXTURE_IDS + (1,)
    # access_audit is deliberately classified below: its task-owned records are
    # append-only and are the only legitimate difference from the seed fixture.
    expected.pop("access_audit")
    # Attendance is classified relationally below; IDs, timestamps and totals
    # are not ownership evidence for the repeatable fixture lifecycle.
    expected.pop("game_attendance_replies")
    for table, ids in expected.items():
        if _ids(connection, table) != ids:
            raise StagingContractError("Officer fixture is partial or drifted")
    empty_tables = (
        (LEGACY_TABLES | PORTAL_TABLES | MOBILE_TABLES)
        - set(expected)
        - {
            "people",
            "access_audit",
            "auth_identities",
            "game_attendance_replies",
            "identity_review_messages",
            "identity_review_threads",
        }
        - MOBILE_TABLES
    )
    if any(_ids(connection, table) for table in empty_tables):
        raise StagingContractError("Officer fixture contains unknown rows")
    if not _mobile_history_is_exact(connection):
        raise StagingContractError("Officer fixture mobile history is drifted")
    _google_recovery_fingerprint(connection)

    people = (
        connection.execute(
            text(
                "SELECT id, formal_name, display_name, admin_note, portal_access_level, "
                "portal_status, version FROM ntubtob.people "
                "WHERE id BETWEEN -112003 AND -112001 ORDER BY id"
            )
        )
        .mappings()
        .all()
    )
    static_people = {-112003: "虛構 Staging 隊友乙", -112002: "虛構 Staging 隊友甲"}
    if len(people) != 3:
        raise StagingContractError("Officer fixture people are drifted")
    for person in people:
        if person["id"] in static_people:
            display_name = static_people[person["id"]]
            if (
                person["formal_name"],
                person["display_name"],
                person["admin_note"],
                person["portal_access_level"],
                person["portal_status"],
                person["version"],
            ) != (None, display_name, None, "basic", "active", 1):
                raise StagingContractError("Officer fixture people are drifted")
    tester = next(
        (person for person in people if person["id"] == OFFICER_PERSON_ID), None
    )
    if tester is None or (
        tester["formal_name"],
        tester["display_name"],
        tester["admin_note"],
        tester["portal_status"],
    ) != (None, "虛構 Staging 測試員", None, "active"):
        raise StagingContractError("Officer fixture tester is drifted")
    identity = (
        connection.execute(
            text(
                "SELECT id, provider, provider_subject, person_id, status "
                "FROM ntubtob.auth_identities "
                "WHERE id=:id"
            ),
            {"id": OFFICER_IDENTITY_ID},
        )
        .mappings()
        .one_or_none()
    )
    if identity != {
        "id": OFFICER_IDENTITY_ID,
        "provider": "line",
        "provider_subject": private_subject,
        "person_id": OFFICER_PERSON_ID,
        "status": "linked",
    }:
        raise StagingContractError("Officer fixture identity is drifted")

    if not _legacy_fixture_audit(connection):
        raise StagingContractError("Officer fixture audit or version is drifted")
    role_state = _classify_role_lifecycle(tester, _fixture_audits(connection))
    if (
        allow_runtime_residue
        and role_state == "baseline"
        and _runtime_residue_is_exact(connection)
    ):
        return "runtime_residue"
    if _attendance_lifecycle_state(connection) and not allow_attendance_reset:
        raise StagingContractError("Officer fixture attendance is drifted")
    return role_state


def officer_inventory(approval: dict, database_url: str, private_subject: str) -> dict:
    private_subject = _officer_subject(private_subject)
    identity = validate_database_identity(
        database_url,
        approval["database_identity_sha256"],
        approval["production_database_identity_sha256"],
        approval["database_provider"],
        approval["database_resource_id"],
    )
    engine = create_engine(database_url)
    try:
        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                    state = _officer_fixture_state(connection, private_subject)
                finally:
                    transaction.rollback()
        except SQLAlchemyError:
            raise StagingContractError(
                "Remote staging Officer inventory failed safely"
            ) from None
    finally:
        engine.dispose()
    return {"database_identity_sha256": identity.fingerprint, "state": state}


def _mobile_principal_state(
    expected_person: dict | None,
    sessions: dict,
    valid_officer_generation: bool | None = None,
) -> dict:
    total = sessions["total"]
    expected = sessions["expected_tuple"]
    mismatch = sessions["expected_person_binding_mismatch"]
    other = sessions["other_principal"]
    if any(type(value) is not int or value < 0 for value in sessions.values()):
        raise StagingContractError("Mobile principal aggregate is invalid")
    if expected + mismatch + other != total:
        raise StagingContractError("Mobile principal aggregate is not exhaustive")
    if mismatch:
        state = "binding_drift"
    elif total == 0:
        state = "no_active_sessions"
    elif expected == total:
        state = "expected_only"
    elif other == total:
        state = "other_only"
    else:
        state = "mixed_principals"
    person = expected_person or {}
    access_level = person.get("portal_access_level")
    status = person.get("portal_status")
    version = person.get("version")
    if valid_officer_generation is None:
        valid_officer_generation = version == 2
    return {
        "state": state,
        "expected_person_match": (
            access_level == "officer"
            and status == "active"
            and valid_officer_generation
        ),
        "expected_person": {
            "access_level": access_level,
            "status": status,
            "version": version,
        },
        "active_sessions": dict(sessions),
    }


def mobile_principal_inventory(approval: dict, database_url: str) -> dict:
    if approval["approval_phase"] != "candidate":
        raise StagingContractError(
            "Mobile principal inventory requires candidate approval"
        )
    validate_database_identity(
        database_url,
        approval["database_identity_sha256"],
        approval["production_database_identity_sha256"],
        approval["database_provider"],
        approval["database_resource_id"],
    )
    engine = create_engine(database_url)
    try:
        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                    revisions = tuple(
                        connection.scalars(
                            text("SELECT version_num FROM ntubtob.alembic_version")
                        )
                    )
                    if revisions != (REVISION,):
                        raise StagingContractError(
                            "Mobile principal inventory requires exact revision 0008"
                        )
                    expected_person = (
                        connection.execute(
                            text(
                                "SELECT portal_access_level, portal_status, version "
                                "FROM ntubtob.people WHERE id=-112001"
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    valid_officer_generation = False
                    if expected_person is not None:
                        valid_officer_generation = (
                            _classify_role_lifecycle(
                                dict(expected_person), _fixture_audits(connection)
                            )
                            == "granted"
                        )
                    sessions = (
                        connection.execute(
                            text(
                                "SELECT "
                                "count(*) FILTER (WHERE s.status='active') AS total, "
                                "count(*) FILTER (WHERE s.status='active' "
                                "AND s.person_id=-112001 "
                                "AND i.status='linked' AND i.person_id=s.person_id "
                                "AND i.provider IN ('line', 'google')) "
                                "AS expected_tuple, "
                                "count(*) FILTER (WHERE s.status='active' "
                                "AND s.person_id=-112001 AND ("
                                "i.status='linked' AND i.person_id=s.person_id "
                                "AND i.provider IN ('line', 'google')) "
                                "IS NOT TRUE) "
                                "AS expected_person_binding_mismatch, "
                                "count(*) FILTER (WHERE s.status='active' "
                                "AND s.person_id<>-112001) AS other_principal "
                                "FROM ntubtob.mobile_sessions s "
                                "LEFT JOIN ntubtob.auth_identities i "
                                "ON i.id=s.auth_identity_id"
                            )
                        )
                        .mappings()
                        .one()
                    )
                    result = _mobile_principal_state(
                        dict(expected_person) if expected_person else None,
                        dict(sessions),
                        valid_officer_generation,
                    )
                finally:
                    transaction.rollback()
        except StagingContractError:
            raise
        except SQLAlchemyError:
            raise StagingContractError(
                "Remote staging mobile principal inventory failed safely"
            ) from None
    finally:
        engine.dispose()
    return result


def runtime_residue_inventory(
    approval: dict, database_url: str, private_subject: str
) -> dict:
    private_subject = _officer_subject(private_subject)
    identity = validate_database_identity(
        database_url,
        approval["database_identity_sha256"],
        approval["production_database_identity_sha256"],
        approval["database_provider"],
        approval["database_resource_id"],
    )
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                state = _officer_fixture_state(connection, private_subject, True)
            finally:
                transaction.rollback()
    except (SQLAlchemyError, StagingContractError):
        raise StagingContractError(
            "Remote staging runtime residue inventory failed safely"
        ) from None
    finally:
        engine.dispose()
    if state == "runtime_residue":
        state = "required"
    elif state == "baseline":
        state = "repaired"
    else:
        raise StagingContractError("Remote staging runtime residue state is not exact")
    return {
        "database_identity_sha256": identity.fingerprint,
        "state": state,
        "residue_rows": 2 if state == "required" else 0,
    }


def execute_runtime_residue_repair(
    approval: dict, database_url: str, private_subject: str
) -> dict:
    if approval["approval_phase"] != "candidate":
        raise StagingContractError(
            "Remote runtime residue repair requires candidate approval"
        )
    private_subject = _officer_subject(private_subject)
    before = runtime_residue_inventory(approval, database_url, private_subject)
    if before["state"] == "repaired":
        return {**before, "removed_residue_rows": 0}
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            if (
                _officer_fixture_state(connection, private_subject, True)
                != "runtime_residue"
            ):
                raise StagingContractError(
                    "Remote runtime residue changed before mutation"
                )
            deleted = connection.execute(
                text(
                    "DELETE FROM ntubtob.game_attendance_replies WHERE "
                    "(id=:id3 AND game_id=:game AND user_id IS NULL AND "
                    "member_id IS NULL AND person_id=:person AND reply=:reply3 "
                    "AND updated_at=:at3) OR (id=:id4 AND game_id=:game AND "
                    "user_id IS NULL AND member_id IS NULL AND person_id=:person "
                    "AND reply=:reply4 AND updated_at=:at4)"
                ),
                {
                    "id3": 3,
                    "id4": 4,
                    "game": -112001,
                    "person": -112001,
                    "reply3": 5,
                    "reply4": 1,
                    "at3": RUNTIME_RESIDUE_ROWS[0][6],
                    "at4": RUNTIME_RESIDUE_ROWS[1][6],
                },
            ).rowcount
            if (
                deleted != 2
                or _officer_fixture_state(connection, private_subject) != "baseline"
            ):
                raise StagingContractError(
                    "Remote runtime residue repair postcheck failed"
                )
    except (SQLAlchemyError, StagingContractError):
        raise StagingContractError(
            "Remote staging runtime residue repair failed safely"
        ) from None
    finally:
        engine.dispose()
    return {
        **runtime_residue_inventory(approval, database_url, private_subject),
        "removed_residue_rows": 2,
    }


def _write_officer_transition(
    connection, transition: str, expected_version: int
) -> None:
    before, after = (
        ("basic", "officer") if transition == "grant" else ("officer", "basic")
    )
    result = connection.execute(
        text(
            "UPDATE ntubtob.people SET portal_access_level=:after, "
            "version=version+1, updated_at=timezone('utc', now()) "
            "WHERE id=:id AND portal_access_level=:before AND "
            "portal_status='active' AND version=:version"
        ),
        {
            "id": OFFICER_PERSON_ID,
            "before": before,
            "after": after,
            "version": expected_version,
        },
    )
    if result.rowcount != 1:
        raise StagingContractError("Officer fixture transition is not exact")
    legacy = (transition, expected_version) in {("grant", 1), ("restore", 2)}
    audit = (
        _legacy_audit(transition)
        if legacy
        else _lifecycle_audit(expected_version, transition)
    )
    id_column = "id, " if legacy else ""
    id_value = ":id, " if legacy else ""
    values = {
        "target": OFFICER_PERSON_ID,
        "identity": OFFICER_IDENTITY_ID,
        "before_state": json.dumps(audit["before_state"], sort_keys=True),
        "after_state": json.dumps(audit["after_state"], sort_keys=True),
        "reason": audit["reason"],
        "request_id": audit["request_id"],
    }
    if legacy:
        values["id"] = audit["id"]
    if not legacy:
        connection.execute(
            text("LOCK TABLE ntubtob.access_audit IN SHARE ROW EXCLUSIVE MODE")
        )
        connection.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('ntubtob.access_audit', 'id'), "
                "GREATEST((SELECT COALESCE(MAX(id), 0) "
                "FROM ntubtob.access_audit), 1), true)"
            )
        )
    connection.execute(
        text(
            "INSERT INTO ntubtob.access_audit "
            f"({id_column}action, actor_person_id, target_person_id, "
            "auth_identity_id, before_state, after_state, reason, request_id, "
            f"created_at) VALUES ({id_value}'access_changed', NULL, :target, "
            ":identity, CAST(:before_state AS json), CAST(:after_state AS json), "
            ":reason, :request_id, timezone('utc', now()))"
        ),
        values,
    )


def _execute_officer_transition(
    approval: dict, database_url: str, private_subject: str, transition: str
) -> dict:
    if approval["approval_phase"] != "candidate":
        raise StagingContractError(
            "Remote Officer transition requires candidate approval"
        )
    private_subject = _officer_subject(private_subject)
    before = officer_inventory(approval, database_url, private_subject)
    terminal_state = "granted" if transition == "grant" else "restored"
    if before["state"] == terminal_state:
        return {**before, "changed": False}
    allowed_states = {"baseline", "restored"} if transition == "grant" else {"granted"}
    if before["state"] not in allowed_states:
        raise StagingContractError("Remote Officer transition state is not exact")
    engine = create_engine(database_url)
    try:
        try:
            with engine.begin() as connection:
                current_state = _officer_fixture_state(connection, private_subject)
                if current_state not in allowed_states:
                    raise StagingContractError(
                        "Remote Officer transition changed before mutation"
                    )
                expected_version = connection.scalar(
                    text("SELECT version FROM ntubtob.people WHERE id=:id"),
                    {"id": OFFICER_PERSON_ID},
                )
                _write_officer_transition(connection, transition, expected_version)
                if (
                    _officer_fixture_state(connection, private_subject)
                    != terminal_state
                ):
                    raise StagingContractError(
                        "Remote Officer transition postcheck failed"
                    )
        except StagingContractError:
            raise
        except (SQLAlchemyError, UnicodeError):
            raise StagingContractError(
                "Remote staging Officer transition failed safely; inspect before retry"
            ) from None
    finally:
        engine.dispose()
    return {
        **officer_inventory(approval, database_url, private_subject),
        "changed": True,
    }


def grant_officer(approval: dict, database_url: str, private_subject: str) -> dict:
    return _execute_officer_transition(approval, database_url, private_subject, "grant")


def restore_basic(approval: dict, database_url: str, private_subject: str) -> dict:
    return _execute_officer_transition(
        approval, database_url, private_subject, "restore"
    )


def _fixture_lifecycle_state(connection, private_subject: str) -> str:
    role_state = _officer_fixture_state(
        connection, private_subject, allow_attendance_reset=True
    )
    if _attendance_lifecycle_state(connection):
        return "reset_required"
    return "ready_officer" if role_state == "granted" else "ready_basic"


def fixture_lifecycle_inventory(
    approval: dict, database_url: str, private_subject: str
) -> dict:
    private_subject = _officer_subject(private_subject)
    identity = validate_database_identity(
        database_url,
        approval["database_identity_sha256"],
        approval["production_database_identity_sha256"],
        approval["database_provider"],
        approval["database_resource_id"],
    )
    engine = create_engine(database_url)
    try:
        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                    state = _fixture_lifecycle_state(connection, private_subject)
                finally:
                    transaction.rollback()
        except StagingContractError:
            raise
        except SQLAlchemyError:
            raise StagingContractError(
                "Remote staging fixture lifecycle inventory failed safely"
            ) from None
    finally:
        engine.dispose()
    return {"database_identity_sha256": identity.fingerprint, "state": state}


def _lock_fixture_roots(connection) -> None:
    people = tuple(
        connection.scalars(
            text(
                "SELECT id FROM ntubtob.people WHERE id = ANY(:ids) "
                "ORDER BY id FOR UPDATE"
            ),
            {"ids": list(MOBILE_FIXTURE_IDS)},
        )
    )
    games = tuple(
        connection.scalars(
            text(
                "SELECT id FROM ntubtob.games WHERE id = ANY(:ids) "
                "ORDER BY id FOR UPDATE"
            ),
            {"ids": list(MOBILE_FIXTURE_IDS)},
        )
    )
    identities = tuple(
        connection.scalars(
            text(
                "SELECT id FROM ntubtob.auth_identities WHERE id = ANY(:ids) "
                "ORDER BY id FOR UPDATE"
            ),
            {"ids": list(MOBILE_FIXTURE_IDS)},
        )
    )
    if (people, games, identities) != (
        MOBILE_FIXTURE_IDS,
        MOBILE_FIXTURE_IDS,
        MOBILE_FIXTURE_IDS,
    ):
        raise StagingContractError("Fixture lifecycle roots are drifted")


def _reconstruct_fixture_attendance(connection) -> None:
    _attendance_lifecycle_state(connection)
    connection.execute(
        text(
            "DELETE FROM ntubtob.game_attendance_replies "
            "WHERE NOT (id = ANY(:canonical_ids)) "
            "AND person_id = ANY(:fixture_ids) AND game_id = ANY(:fixture_ids)"
        ),
        {
            "canonical_ids": list(CANONICAL_ATTENDANCE),
            "fixture_ids": list(MOBILE_FIXTURE_IDS),
        },
    )
    for row_id, expected in CANONICAL_ATTENDANCE.items():
        connection.execute(
            text(
                "INSERT INTO ntubtob.game_attendance_replies "
                "(id, game_id, user_id, member_id, person_id, reply, updated_at) "
                "VALUES (:id, :game_id, NULL, NULL, :person_id, :reply, "
                "timezone('utc', now())) ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": row_id,
                "game_id": expected["game_id"],
                "person_id": expected["person_id"],
                "reply": expected["reply"],
            },
        )
        connection.execute(
            text(
                "UPDATE ntubtob.game_attendance_replies SET reply=:reply, "
                "updated_at=CASE WHEN reply<>:reply THEN timezone('utc', now()) "
                "ELSE updated_at END WHERE id=:id AND game_id=:game_id "
                "AND user_id IS NULL AND member_id IS NULL AND person_id=:person_id"
            ),
            {
                "id": row_id,
                "game_id": expected["game_id"],
                "person_id": expected["person_id"],
                "reply": expected["reply"],
            },
        )
    if not _attendance_is_canonical(connection):
        raise StagingContractError(
            "Remote fixture lifecycle attendance postcheck failed"
        )


def execute_fixture_lifecycle_reset(
    approval: dict, database_url: str, private_subject: str
) -> dict:
    if approval["approval_phase"] != "candidate":
        raise StagingContractError(
            "Remote fixture lifecycle reset requires candidate approval"
        )
    private_subject = _officer_subject(private_subject)
    before = fixture_lifecycle_inventory(approval, database_url, private_subject)
    if before["state"] == "ready_basic":
        return {**before, "changed": False}
    engine = create_engine(database_url)
    try:
        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(
                        text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    )
                    _lock_fixture_roots(connection)
                    current = _fixture_lifecycle_state(connection, private_subject)
                    if current not in {"ready_officer", "reset_required"}:
                        raise StagingContractError(
                            "Remote fixture lifecycle changed before reset"
                        )
                    role_state = _officer_fixture_state(
                        connection, private_subject, allow_attendance_reset=True
                    )
                    if role_state == "granted":
                        version = connection.scalar(
                            text("SELECT version FROM ntubtob.people WHERE id=:id"),
                            {"id": OFFICER_PERSON_ID},
                        )
                        _write_officer_transition(connection, "restore", version)
                    _reconstruct_fixture_attendance(connection)
                    if (
                        _fixture_lifecycle_state(connection, private_subject)
                        != "ready_basic"
                    ):
                        raise StagingContractError(
                            "Remote fixture lifecycle reset postcheck failed"
                        )
                    transaction.commit()
                except Exception:
                    if transaction.is_active:
                        transaction.rollback()
                    raise
        except (SQLAlchemyError, StagingContractError):
            raise StagingContractError(
                "Remote staging fixture lifecycle reset failed safely; inspect before retry"
            ) from None
    finally:
        engine.dispose()
    return {
        **fixture_lifecycle_inventory(approval, database_url, private_subject),
        "changed": True,
    }


def _broker_schema_call(function, *args):
    """Run one existing bounded broker call against the current staging schema."""
    return function(*args)


def broker_fixture_lifecycle_inventory(
    approval: dict, database_url: str, private_subject: str
) -> dict:
    return _broker_schema_call(
        fixture_lifecycle_inventory, approval, database_url, private_subject
    )


def broker_grant_officer(
    approval: dict, database_url: str, private_subject: str
) -> dict:
    return _broker_schema_call(grant_officer, approval, database_url, private_subject)


def broker_restore_basic(
    approval: dict, database_url: str, private_subject: str
) -> dict:
    return _broker_schema_call(restore_basic, approval, database_url, private_subject)


def broker_reset_fixture_lifecycle(
    approval: dict, database_url: str, private_subject: str
) -> dict:
    return _broker_schema_call(
        execute_fixture_lifecycle_reset, approval, database_url, private_subject
    )


def plan(approval: dict, database_url: str) -> dict:
    validate_database_identity(
        database_url,
        approval["database_identity_sha256"],
        approval["production_database_identity_sha256"],
        approval["database_provider"],
        approval["database_resource_id"],
    )
    return {
        "operation": "empty-bootstrap-migration-seed-postcheck",
        "revision": REVISION,
        "database_alias": approval["database_alias"],
        "database_provider": approval["database_provider"],
        "database_identity_sha256": approval["database_identity_sha256"],
        "provider_subject": "private-input-redacted",
        "mutation": "none-dry-run",
    }


def inventory(approval: dict, database_url: str) -> dict:
    identity = validate_database_identity(
        database_url,
        approval["database_identity_sha256"],
        approval["production_database_identity_sha256"],
        approval["database_provider"],
        approval["database_resource_id"],
    )
    engine = create_engine(database_url)
    try:
        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                    state = _database_state(connection)
                finally:
                    transaction.rollback()
        except SQLAlchemyError:
            raise StagingContractError(
                "Remote staging inventory failed safely"
            ) from None
    finally:
        engine.dispose()
    return {"database_identity_sha256": identity.fingerprint, **state}


def _database_state(
    connection, private_subject: str | None = None, include_fingerprint: bool = False
) -> dict:
    schema_exists = connection.scalar(
        text("SELECT to_regnamespace('ntubtob') IS NOT NULL")
    )
    if not schema_exists:
        return {
            "revision": None,
            "database_state": "empty",
            "fixture_state": "clean",
        }
    revisions = tuple(
        connection.scalars(text("SELECT version_num FROM ntubtob.alembic_version"))
    )
    if len(revisions) != 1 or revisions[0] not in REVISION_TABLES:
        raise StagingContractError(
            "Remote staging revision is unknown or drifted; do not retry"
        )
    revision = revisions[0]
    tables = tuple(
        connection.scalars(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='ntubtob' ORDER BY table_name"
            )
        )
    )
    if set(tables) != REVISION_TABLES[revision]:
        raise StagingContractError(
            "Remote staging schema is partial or drifted; do not retry"
        )
    fixture_state, fixture_fingerprint = _canonical_fixture_fingerprint(
        connection, revision, private_subject
    )
    state = {
        "revision": revision,
        "database_state": "ready" if revision == REVISION else "upgrade_pending",
        "fixture_state": fixture_state,
    }
    if include_fingerprint:
        state["fixture_fingerprint"] = fixture_fingerprint
    return state


def _ids(connection, table: str) -> tuple:
    return tuple(
        connection.scalars(text(f"SELECT id FROM ntubtob.{table} ORDER BY id"))
    )


def _fixture_state(connection) -> str:
    people_ids = _ids(connection, "people")
    if people_ids == LEGACY_IDS["people"]:
        state = "clean"
        mobile_ids = ()
    elif people_ids == MOBILE_FIXTURE_IDS + LEGACY_IDS["people"]:
        state = "seeded"
        mobile_ids = MOBILE_FIXTURE_IDS
    else:
        raise StagingContractError(
            "Remote staging fixture is partial or drifted; do not retry"
        )
    expected = dict(LEGACY_IDS)
    expected["attendance_reply_types"] = (
        (1, 2, 3, 4, 5) + LEGACY_IDS["attendance_reply_types"]
        if state == "seeded"
        else LEGACY_IDS["attendance_reply_types"]
    )
    expected["games"] = mobile_ids + LEGACY_IDS["games"]
    expected["game_attendance_replies"] = (
        mobile_ids + LEGACY_IDS["game_attendance_replies"]
    )
    expected["people"] = mobile_ids + LEGACY_IDS["people"]
    expected["person_qualifications"] = mobile_ids + (1,)
    if state == "seeded":
        # A seeded fixture may carry the exact append-only TASK-119/TASK-126
        # role lifecycle. Its complete shape is validated below rather than by
        # an ID-only equality check.
        expected.pop("access_audit")
    for table, ids in expected.items():
        if _ids(connection, table) != ids:
            raise StagingContractError(
                f"Remote staging fixture table is drifted: {table}; do not retry"
            )
    lifecycle_tables = {"people", "access_audit"}
    if state == "seeded":
        # Exact tester-owned mobile history is dynamic and is validated and
        # fingerprinted below. A clean fixture still requires every mobile
        # table to be empty.
        lifecycle_tables |= MOBILE_TABLES | {
            "auth_identities",
            "identity_review_messages",
            "identity_review_threads",
        }
    empty_tables = (
        (LEGACY_TABLES | PORTAL_TABLES | MOBILE_TABLES)
        - set(expected)
        - lifecycle_tables
    )
    if any(_ids(connection, table) for table in empty_tables):
        raise StagingContractError(
            "Remote staging fixture contains unknown rows; do not retry"
        )
    members = connection.execute(
        text("SELECT id, person_id FROM ntubtob.members ORDER BY id")
    ).all()
    unresolved = connection.scalar(
        text(
            "SELECT count(*) FROM ntubtob.game_attendance_replies "
            "WHERE id BETWEEN 9601 AND 9604 AND person_id IS DISTINCT FROM 1"
        )
    )
    if members != [(9201, 1), (9202, None)] or unresolved:
        raise StagingContractError(
            "Remote staging legacy backfill is drifted; do not retry"
        )
    return state


def _canonical_fixture_fingerprint(
    connection, revision: str, private_subject: str | None = None
) -> tuple[str, tuple]:
    """Validate the complete owned fixture and return a secret-free fingerprint."""
    state = _fixture_state(connection)
    broker_history_fingerprint = ()
    if BROKER_TABLES <= REVISION_TABLES[revision]:
        broker_rows = connection.execute(
            text(
                "SELECT * FROM ntubtob.staging_broker_operations "
                "ORDER BY operation_id"
            )
        ).all()
        if broker_rows and (
            state != "seeded"
            or any(
                row._mapping["lifecycle_state"] != "postcheck_complete"
                or row._mapping["reason_code"] is not None
                for row in broker_rows
            )
        ):
            raise StagingContractError(
                "Remote staging broker history is not terminal; do not retry"
            )
        broker_history_fingerprint = tuple(map(tuple, broker_rows))
    notification_tables = NOTIFICATION_TABLES & REVISION_TABLES[revision]
    if any(
        connection.scalar(text(f"SELECT count(*) FROM ntubtob.{table}"))
        for table in notification_tables
    ):
        raise StagingContractError(
            "Remote staging fixture contains owned runtime rows; do not retry"
        )
    legacy_fingerprint = _canonical_legacy_fingerprint(connection, state)
    if state == "clean":
        return state, ("clean", legacy_fingerprint, broker_history_fingerprint)

    people = connection.execute(
        text(
            "SELECT id, formal_name, display_name, admin_note, portal_access_level, "
            "portal_status, version, created_at, updated_at FROM ntubtob.people "
            "WHERE id = ANY(:ids) ORDER BY id"
        ),
        {"ids": list(MOBILE_FIXTURE_IDS)},
    ).all()
    expected_people = (
        (
            -112003,
            None,
            "虛構 Staging 隊友乙",
            None,
            "basic",
            "active",
            1,
            ANCHOR,
            ANCHOR,
        ),
        (
            -112002,
            None,
            "虛構 Staging 隊友甲",
            None,
            "basic",
            "active",
            1,
            ANCHOR,
            ANCHOR,
        ),
        (
            -112001,
            None,
            "虛構 Staging 測試員",
            None,
            "active",
            ANCHOR,
        ),
    )
    actual_people = (
        tuple(people[0]),
        tuple(people[1]),
        tuple(value for index, value in enumerate(people[2]) if index not in {4, 6, 8}),
    )
    if actual_people != expected_people:
        raise StagingContractError(
            "Remote staging fixture people are drifted; do not retry"
        )

    audits = _fixture_audits(connection)
    try:
        google_recovery_fingerprint = _google_recovery_fingerprint(connection)
    except StagingContractError:
        raise StagingContractError(
            "Remote staging fixture Google recovery graph is drifted; do not retry"
        ) from None
    if any(row["created_at"] is None for row in audits):
        raise StagingContractError(
            "Remote staging fixture table is drifted: access_audit; do not retry"
        )
    tester = dict(people[2]._mapping)
    try:
        _classify_role_lifecycle(tester, audits)
    except StagingContractError:
        raise StagingContractError(
            "Remote staging fixture table is drifted: access_audit; do not retry"
        ) from None
    expected_tester_updated_at = audits[-1]["created_at"] if audits else ANCHOR
    if tester["updated_at"] != expected_tester_updated_at:
        raise StagingContractError(
            "Remote staging fixture people are drifted; do not retry"
        )
    audit_fingerprint = tuple(
        tuple(row[field] for field in (*AUDIT_FIELDS, "created_at")) for row in audits
    )
    if not _mobile_history_is_exact(connection):
        raise StagingContractError(
            "Remote staging fixture mobile history is drifted; do not retry"
        )
    mobile_history_fingerprint = tuple(
        (
            table,
            tuple(
                map(
                    tuple,
                    connection.execute(
                        text(f"SELECT * FROM ntubtob.{table} ORDER BY id")
                    ).all(),
                )
            ),
        )
        for table in sorted(MOBILE_TABLES)
    )

    identities = connection.execute(
        text(
            "SELECT id, provider, person_id, status, created_at, updated_at "
            "FROM ntubtob.auth_identities "
            "WHERE id = ANY(:ids) ORDER BY id"
        ),
        {"ids": list(MOBILE_FIXTURE_IDS)},
    ).all()
    if tuple(map(tuple, identities)) != tuple(
        (fixture_id, "line", fixture_id, "linked", ANCHOR, ANCHOR)
        for fixture_id in MOBILE_FIXTURE_IDS
    ):
        raise StagingContractError(
            "Remote staging fixture identities are drifted; do not retry"
        )
    if private_subject is None:
        tester_binding = connection.scalar(
            text(
                "SELECT count(*)=1 FROM ntubtob.auth_identities WHERE id=-112001 "
                "AND provider='line' AND person_id=-112001 AND status='linked' "
                "AND length(provider_subject) BETWEEN 8 AND 255 "
                "AND provider_subject NOT IN ('task112-fictional-teammate-a', "
                "'task112-fictional-teammate-b')"
            )
        )
    else:
        tester_binding = connection.scalar(
            text(
                "SELECT count(*)=1 FROM ntubtob.auth_identities WHERE id=-112001 "
                "AND provider='line' AND provider_subject=:subject "
                "AND person_id=-112001 AND status='linked'"
            ),
            {"subject": private_subject},
        )
    teammate_bindings = connection.scalar(
        text(
            "SELECT count(*)=2 FROM ntubtob.auth_identities WHERE "
            "(id=-112002 AND provider_subject='task112-fictional-teammate-a' "
            "AND person_id=-112002) OR "
            "(id=-112003 AND provider_subject='task112-fictional-teammate-b' "
            "AND person_id=-112003)"
        )
    )
    if tester_binding is not True or teammate_bindings is not True:
        raise StagingContractError(
            "Remote staging fixture identity binding is drifted; do not retry"
        )
    identity_fingerprint = tuple(
        map(
            tuple,
            connection.execute(
                text("SELECT * FROM ntubtob.auth_identities ORDER BY id")
            ).all(),
        )
    )

    qualifications = connection.execute(
        text(
            "SELECT id, person_id, qualification, status, valid_from, valid_until, "
            "granted_by_person_id, reason, created_at, updated_at "
            "FROM ntubtob.person_qualifications WHERE id = ANY(:ids) ORDER BY id"
        ),
        {"ids": list(MOBILE_FIXTURE_IDS)},
    ).all()
    expected_qualifications = tuple(
        (
            fixture_id,
            fixture_id,
            "guest_player",
            "active",
            datetime(2034, 1, 1, tzinfo=timezone.utc),
            datetime(2038, 1, 1, tzinfo=timezone.utc),
            None,
            "fictional staging",
            ANCHOR,
            ANCHOR,
        )
        for fixture_id in MOBILE_FIXTURE_IDS
    )
    if tuple(map(tuple, qualifications)) != expected_qualifications:
        raise StagingContractError(
            "Remote staging qualifications are drifted; do not retry"
        )

    games = connection.execute(
        text(
            "SELECT id, year, season, start_datetime, duration, location, home_team, "
            "away_team, invitation_time, cancellation_time, cancellation_announcement_time "
            "FROM ntubtob.games WHERE id = ANY(:ids) ORDER BY id"
        ),
        {"ids": list(MOBILE_FIXTURE_IDS)},
    ).all()
    expected_games = (
        (
            -112003,
            2035,
            1,
            datetime(2035, 2, 15, 4, tzinfo=timezone.utc),
            150,
            "虛構球場 C",
            "台大OB",
            "虛構對手丙",
            ANCHOR,
            None,
            None,
        ),
        (
            -112002,
            2035,
            1,
            datetime(2035, 2, 8, 3, tzinfo=timezone.utc),
            150,
            "虛構球場 B",
            "虛構對手乙",
            "台大OB",
            ANCHOR,
            None,
            None,
        ),
        (
            -112001,
            2035,
            1,
            datetime(2035, 2, 1, 2, tzinfo=timezone.utc),
            150,
            "虛構球場 A",
            "台大OB",
            "虛構對手甲",
            ANCHOR,
            None,
            None,
        ),
    )
    if tuple(map(tuple, games)) != expected_games:
        raise StagingContractError("Remote staging games are drifted; do not retry")

    replies = connection.execute(
        text(
            "SELECT id, game_id, user_id, member_id, person_id, reply, updated_at "
            "FROM ntubtob.game_attendance_replies WHERE id = ANY(:ids) ORDER BY id"
        ),
        {"ids": list(MOBILE_FIXTURE_IDS)},
    ).all()
    if tuple(map(tuple, replies)) != CANONICAL_FIXTURE_REPLY_ROWS:
        raise StagingContractError("Remote staging attendance is drifted; do not retry")
    return state, (
        "seeded",
        legacy_fingerprint,
        tuple(map(tuple, people)),
        audit_fingerprint,
        google_recovery_fingerprint,
        broker_history_fingerprint,
        mobile_history_fingerprint,
        identity_fingerprint,
        bool(tester_binding),
        tuple(map(tuple, qualifications)),
        tuple(map(tuple, games)),
        tuple(map(tuple, replies)),
    )


def _canonical_legacy_fingerprint(connection, fixture_state: str) -> tuple:
    """Validate repository-owned legacy rows, including dynamic migration timestamps."""
    reply_types = connection.execute(
        text("SELECT id, description FROM ntubtob.attendance_reply_types ORDER BY id")
    ).all()
    expected_reply_types = (
        (
            (1, "TASK112 fixture attending"),
            (2, "TASK112 fixture not_attending"),
            (3, "TASK112 fixture arriving_late"),
            (4, "TASK112 fixture leaving_early"),
            (5, "TASK112 fixture undecided"),
        )
        if fixture_state == "seeded"
        else ()
    ) + (
        (9101, "fictional attending"),
        (9102, "fictional not attending"),
        (9103, "fictional maybe"),
    )
    if tuple(map(tuple, reply_types)) != expected_reply_types:
        raise StagingContractError(
            "Remote staging legacy reply types are drifted; do not retry"
        )

    ballparks = connection.execute(
        text(
            "SELECT id, name, city_name, city_weather_code, district_name "
            "FROM ntubtob.ballparks ORDER BY id"
        )
    ).all()
    if tuple(map(tuple, ballparks)) != (
        (9301, "虛構球場", "虛構城市", "fictional-code", "虛構行政區"),
    ):
        raise StagingContractError(
            "Remote staging legacy ballparks are drifted; do not retry"
        )

    members = connection.execute(
        text(
            "SELECT id, name, enroll_year, major, number, positions, person_id "
            "FROM ntubtob.members ORDER BY id"
        )
    ).all()
    if tuple(map(tuple, members)) != (
        (9201, "虛構校友甲", 100, "虛構系所", 1, "虛構守位", 1),
        (9202, "虛構校友乙", 101, "虛構系所", 2, "虛構守位", None),
    ):
        raise StagingContractError(
            "Remote staging legacy members are drifted; do not retry"
        )

    games = connection.execute(
        text(
            "SELECT id, year, season, start_datetime, duration, location, home_team, "
            "away_team, invitation_time, cancellation_time, cancellation_announcement_time "
            "FROM ntubtob.games WHERE id IN (9401, 9402) ORDER BY id"
        )
    ).all()
    expected_games = (
        (
            9401,
            126,
            1,
            datetime(2037, 1, 1, 1, tzinfo=timezone.utc),
            180,
            "虛構球場",
            "虛構主隊",
            "虛構客隊",
            None,
            None,
            None,
        ),
        (
            9402,
            126,
            1,
            datetime(2037, 1, 8, 1, tzinfo=timezone.utc),
            180,
            "虛構球場",
            "虛構主隊",
            "虛構客隊",
            datetime(2037, 1, 1, 1, tzinfo=timezone.utc),
            datetime(2037, 1, 2, 1, tzinfo=timezone.utc),
            None,
        ),
    )
    if tuple(map(tuple, games)) != expected_games:
        raise StagingContractError(
            "Remote staging legacy games are drifted; do not retry"
        )

    line_users = connection.execute(
        text(
            "SELECT id, nickname, line_user_id, member_id, submit_time, has_replied, "
            "ignored FROM ntubtob.line_users ORDER BY id"
        )
    ).all()
    line_user_static = tuple(
        (row[0], row[1], row[2], row[3], row[5], row[6]) for row in line_users
    )
    if (
        line_user_static
        != (
            (9501, "虛構已連結", "fake-line-linked", 9201, True, False),
            (9502, "虛構待配對", "fake-line-pending", None, False, False),
            (9503, "虛構已忽略", "fake-line-ignored", None, False, True),
        )
        or len({row[4] for row in line_users}) != 1
        or line_users[0][4] is None
    ):
        raise StagingContractError(
            "Remote staging legacy line users are drifted; do not retry"
        )

    attendance = connection.execute(
        text(
            "SELECT id, game_id, user_id, member_id, person_id, reply, updated_at "
            "FROM ntubtob.game_attendance_replies WHERE id BETWEEN 9601 AND 9604 "
            "ORDER BY id"
        )
    ).all()
    expected_attendance = (
        (9601, 9401, 9501, 9201, 1, 9103, datetime(2037, 1, 1, tzinfo=timezone.utc)),
        (
            9602,
            9401,
            9501,
            9201,
            1,
            9101,
            datetime(2037, 1, 1, 0, 1, tzinfo=timezone.utc),
        ),
        (9603, 9402, 9501, 9201, 1, 9102, datetime(2037, 1, 2, tzinfo=timezone.utc)),
        (
            9604,
            9402,
            9501,
            9201,
            1,
            9102,
            datetime(2037, 1, 2, 0, 1, tzinfo=timezone.utc),
        ),
    )
    if tuple(map(tuple, attendance)) != expected_attendance:
        raise StagingContractError(
            "Remote staging legacy attendance is drifted; do not retry"
        )

    person = connection.execute(
        text(
            "SELECT id, formal_name, display_name, admin_note, portal_access_level, "
            "portal_status, version, created_at, updated_at FROM ntubtob.people "
            "WHERE id=1"
        )
    ).one_or_none()
    if (
        person is None
        or tuple(person[:7])
        != (
            1,
            "虛構校友甲",
            "虛構校友甲",
            None,
            "basic",
            "inactive",
            1,
        )
        or person[7] is None
        or person[7] != person[8]
    ):
        raise StagingContractError(
            "Remote staging legacy person is drifted; do not retry"
        )

    qualification = connection.execute(
        text(
            "SELECT id, person_id, qualification, status, valid_from, valid_until, "
            "granted_by_person_id, reason, created_at, updated_at "
            "FROM ntubtob.person_qualifications WHERE id=1"
        )
    ).one_or_none()
    if (
        qualification is None
        or tuple(qualification[:8])
        != (
            1,
            1,
            "team_player",
            "active",
            None,
            None,
            None,
            "Phase C attendance compatibility backfill",
        )
        or qualification[8] is None
        or qualification[8] != qualification[9]
    ):
        raise StagingContractError(
            "Remote staging legacy qualification is drifted; do not retry"
        )

    audit = (
        connection.execute(
            text(
                "SELECT id, action, actor_person_id, target_person_id, auth_identity_id, "
                "before_state, after_state, reason, request_id, created_at "
                "FROM ntubtob.access_audit WHERE id=1"
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        audit is None
        or _audit_shape(audit)
        != {
            "id": 1,
            "action": "member_backfilled",
            "actor_person_id": None,
            "target_person_id": 1,
            "auth_identity_id": None,
            "before_state": {"member_id": 9201, "person_id": None},
            "after_state": {"member_id": 9201, "person_id": 1},
            "reason": "Phase C attendance compatibility backfill",
            "request_id": "phase-c-attendance-member-9201",
        }
        or audit["created_at"] is None
    ):
        raise StagingContractError(
            "Remote staging legacy audit is drifted; do not retry"
        )
    migration_timestamp = person[7]
    if (
        qualification[8] != migration_timestamp
        or audit["created_at"] != migration_timestamp
    ):
        raise StagingContractError(
            "Remote staging legacy migration timestamps are drifted; do not retry"
        )
    return (
        tuple(map(tuple, reply_types)),
        tuple(map(tuple, ballparks)),
        tuple(map(tuple, members)),
        tuple(map(tuple, games)),
        tuple(map(tuple, line_users)),
        tuple(map(tuple, attendance)),
        tuple(person),
        tuple(qualification),
        tuple(audit[field] for field in (*AUDIT_FIELDS, "created_at")),
    )


def recover(approval: dict, database_url: str) -> dict:
    state = inventory(approval, database_url)
    if state["database_state"] == "empty":
        outcome = "not_started"
    elif state["database_state"] == "upgrade_pending":
        outcome = "upgrade_pending"
    elif state["fixture_state"] == "clean":
        outcome = "seed_pending"
    else:
        outcome = "completed"
    return {"outcome": outcome, **state}


def _alembic_config(root: Path, connection) -> Config:
    config = Config(str(root / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def _bootstrap_empty_database(engine, root: Path) -> None:
    try:
        with engine.begin() as connection:
            if _database_state(connection)["database_state"] != "empty":
                raise StagingContractError(
                    "Remote staging bootstrap requires an exact empty database"
                )
            connection.execute(text(LEGACY_FIXTURE_SQL))
            config = _alembic_config(root, connection)
            command.stamp(config, BASE_REVISION)
            command.upgrade(config, REVISION)
    except StagingContractError:
        raise
    except (CommandError, SQLAlchemyError, UnicodeError):
        raise StagingContractError(
            "Remote staging bootstrap failed safely; recover before retry"
        ) from None


def _upgrade_known_database(
    engine,
    root: Path,
    expected_revision: str,
    expected_fixture_state: str,
    private_subject: str | None = None,
) -> None:
    if expected_revision not in FORWARD_REVISIONS:
        raise StagingContractError("Remote staging forward revision is not approved")
    try:
        with engine.begin() as connection:
            before = _database_state(connection, private_subject, True)
            if (
                before["database_state"] != "upgrade_pending"
                or before["revision"] != expected_revision
                or before["fixture_state"] != expected_fixture_state
            ):
                raise StagingContractError(
                    "Remote staging forward-upgrade precheck drifted"
                )
            command.upgrade(_alembic_config(root, connection), REVISION)
            after = _database_state(connection, private_subject, True)
            if (
                after["database_state"] != "ready"
                or after["revision"] != REVISION
                or after["fixture_state"] != expected_fixture_state
                or after["fixture_fingerprint"] != before["fixture_fingerprint"]
            ):
                raise StagingContractError(
                    "Remote staging forward-upgrade postcheck failed"
                )
    except StagingContractError:
        raise
    except (CommandError, SQLAlchemyError, UnicodeError):
        raise StagingContractError(
            "Remote staging forward upgrade failed safely; recover before retry"
        ) from None


def execute(
    approval: dict,
    database_url: str,
    private_subject: str,
    root: Path,
) -> dict:
    if approval["approval_phase"] != "candidate":
        raise StagingContractError("Remote data mutation requires candidate approval")
    before = recover(approval, database_url)
    if before["outcome"] == "completed":
        raise StagingContractError("Remote data operation already completed")
    engine = create_engine(database_url)
    seed_required = True
    try:
        if before["outcome"] == "not_started":
            _bootstrap_empty_database(engine, root)
            migrated = inventory(approval, database_url)
            if migrated["revision"] != REVISION or migrated["fixture_state"] != "clean":
                raise StagingContractError("Remote staging migration postcheck failed")
        elif before["outcome"] == "upgrade_pending":
            _upgrade_known_database(
                engine,
                root,
                before["revision"],
                before["fixture_state"],
                private_subject,
            )
            migrated = inventory(approval, database_url)
            if (
                migrated["revision"] != REVISION
                or migrated["fixture_state"] != before["fixture_state"]
            ):
                raise StagingContractError(
                    "Remote staging forward-upgrade recovery failed"
                )
            seed_required = before["fixture_state"] == "clean"
        if seed_required:
            seed(engine, private_subject)
    except StagingContractError:
        raise
    except (SQLAlchemyError, StagingSeedError, UnicodeError):
        raise StagingContractError(
            "Remote staging seed failed safely; recover before retry"
        ) from None
    finally:
        engine.dispose()
    result = recover(approval, database_url)
    if result["outcome"] != "completed":
        raise StagingContractError("Remote staging seed postcheck failed")
    return result


def attendance_repair_inventory(approval: dict, database_url: str) -> dict:
    identity = validate_database_identity(
        database_url,
        approval["database_identity_sha256"],
        approval["production_database_identity_sha256"],
        approval["database_provider"],
        approval["database_resource_id"],
    )
    engine = create_engine(database_url)
    try:
        try:
            state = inspect_attendance_repair(engine)
        except (SQLAlchemyError, StagingSeedError, UnicodeError):
            raise StagingContractError(
                "Remote staging attendance repair inventory failed safely"
            ) from None
    finally:
        engine.dispose()
    return {"database_identity_sha256": identity.fingerprint, **state}


def execute_attendance_repair(approval: dict, database_url: str) -> dict:
    if approval["approval_phase"] != "candidate":
        raise StagingContractError(
            "Remote attendance repair requires candidate approval"
        )
    before = attendance_repair_inventory(approval, database_url)
    if before["state"] == "repaired":
        return {**before, "removed_hidden_rows": 0}
    if before != {
        "database_identity_sha256": approval["database_identity_sha256"],
        "state": "required",
        "hidden_rows": 2,
    }:
        raise StagingContractError("Remote attendance repair state is not exact")
    engine = create_engine(database_url)
    try:
        try:
            result = repair_attendance_fixture(engine)
        except (SQLAlchemyError, StagingSeedError, UnicodeError):
            raise StagingContractError(
                "Remote staging attendance repair failed safely; inspect before retry"
            ) from None
    finally:
        engine.dispose()
    after = attendance_repair_inventory(approval, database_url)
    if after["state"] != "repaired" or after["hidden_rows"] != 0:
        raise StagingContractError("Remote staging attendance repair postcheck failed")
    return {**after, "removed_hidden_rows": result["removed_hidden_rows"]}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--inspect-attendance-repair", action="store_true")
    parser.add_argument("--execute-attendance-repair", action="store_true")
    parser.add_argument("--inspect-runtime-residue", action="store_true")
    parser.add_argument("--execute-runtime-residue-repair", action="store_true")
    parser.add_argument("--inspect-fixture-lifecycle", action="store_true")
    parser.add_argument("--reset-fixture-lifecycle", action="store_true")
    parser.add_argument("--inspect-officer", action="store_true")
    parser.add_argument("--inspect-mobile-principal", action="store_true")
    parser.add_argument("--grant-officer", action="store_true")
    parser.add_argument("--restore-basic", action="store_true")
    args = parser.parse_args(argv)
    try:
        approval = load_approval(args.approval)
        database_url = os.environ.get("MOBILE_STAGING_DATABASE_URL", "")
        selected = sum(
            bool(value)
            for value in (
                args.execute,
                args.recover,
                args.inspect_attendance_repair,
                args.execute_attendance_repair,
                args.inspect_runtime_residue,
                args.execute_runtime_residue_repair,
                args.inspect_fixture_lifecycle,
                args.reset_fixture_lifecycle,
                args.inspect_officer,
                args.inspect_mobile_principal,
                args.grant_officer,
                args.restore_basic,
            )
        )
        if selected > 1:
            raise StagingContractError("Choose exactly one staging data action")
        if args.execute_attendance_repair:
            result = execute_attendance_repair(approval, database_url)
        elif args.inspect_attendance_repair:
            result = attendance_repair_inventory(approval, database_url)
        elif args.reset_fixture_lifecycle:
            result = execute_fixture_lifecycle_reset(
                approval,
                database_url,
                os.environ.get("MOBILE_STAGING_PROVIDER_SUBJECT", ""),
            )
        elif args.inspect_fixture_lifecycle:
            result = fixture_lifecycle_inventory(
                approval,
                database_url,
                os.environ.get("MOBILE_STAGING_PROVIDER_SUBJECT", ""),
            )
        elif args.execute_runtime_residue_repair:
            result = execute_runtime_residue_repair(
                approval,
                database_url,
                os.environ.get("MOBILE_STAGING_PROVIDER_SUBJECT", ""),
            )
        elif args.inspect_runtime_residue:
            result = runtime_residue_inventory(
                approval,
                database_url,
                os.environ.get("MOBILE_STAGING_PROVIDER_SUBJECT", ""),
            )
        elif args.inspect_officer:
            result = officer_inventory(
                approval,
                database_url,
                os.environ.get("MOBILE_STAGING_PROVIDER_SUBJECT", ""),
            )
        elif args.inspect_mobile_principal:
            result = mobile_principal_inventory(approval, database_url)
        elif args.grant_officer:
            result = grant_officer(
                approval,
                database_url,
                os.environ.get("MOBILE_STAGING_PROVIDER_SUBJECT", ""),
            )
        elif args.restore_basic:
            result = restore_basic(
                approval,
                database_url,
                os.environ.get("MOBILE_STAGING_PROVIDER_SUBJECT", ""),
            )
        elif args.recover:
            result = recover(approval, database_url)
        elif args.execute:
            result = execute(
                approval,
                database_url,
                os.environ.get("MOBILE_STAGING_PROVIDER_SUBJECT", ""),
                Path(__file__).resolve().parents[1],
            )
        else:
            result = plan(approval, database_url)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (StagingContractError, StagingSeedError, SQLAlchemyError) as error:
        print(f"ERROR: {error}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
