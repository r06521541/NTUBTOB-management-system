"""Approved remote staging migration/fixture operation; dry-run by default."""

from __future__ import annotations

import argparse
import json
import os
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
        REVISION,
        StagingContractError,
        load_approval,
        validate_database_identity,
    )
    from .mobile_staging_seed import (
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
        REVISION,
        StagingContractError,
        load_approval,
        validate_database_identity,
    )
    from mobile_staging_seed import (
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
EXPECTED_TABLES = LEGACY_TABLES | PORTAL_TABLES | MOBILE_TABLES | {"alembic_version"}
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
                "auth_identity_id, before_state, after_state, reason, request_id "
                "FROM ntubtob.access_audit WHERE target_person_id=:person "
                "OR auth_identity_id=:identity ORDER BY "
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
            "WHERE auth_identity_id=-112001 AND person_id=-112001",
        ),
        (
            "mobile_refresh_tokens",
            "SELECT count(*) FROM ntubtob.mobile_refresh_tokens t "
            "JOIN ntubtob.mobile_sessions s ON s.id=t.session_id "
            "WHERE s.auth_identity_id=-112001 AND s.person_id=-112001",
        ),
        (
            "mobile_refresh_attempts",
            "SELECT count(*) FROM ntubtob.mobile_refresh_attempts a "
            "JOIN ntubtob.mobile_sessions s ON s.id=a.session_id "
            "WHERE s.auth_identity_id=-112001 AND s.person_id=-112001",
        ),
        (
            "mobile_auth_exchanges",
            "SELECT count(*) FROM ntubtob.mobile_auth_exchanges e "
            "JOIN ntubtob.mobile_sessions s ON s.id=e.session_id "
            "WHERE e.provider='line' AND s.auth_identity_id=-112001 "
            "AND s.person_id=-112001",
        ),
        (
            "mobile_idempotency_records",
            "SELECT count(*) FROM ntubtob.mobile_idempotency_records i "
            "JOIN ntubtob.mobile_sessions s ON s.id=i.session_id "
            "WHERE i.person_id=-112001 AND s.auth_identity_id=-112001 "
            "AND s.person_id=-112001",
        ),
    )
    for table, owned_query in checks:
        total = connection.scalar(text(f"SELECT count(*) FROM ntubtob.{table}"))
        if connection.scalar(text(owned_query)) != total:
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
    if set(tables) != EXPECTED_TABLES or revisions != (REVISION,):
        raise StagingContractError("Officer fixture is not ready; do not retry")

    expected = dict(LEGACY_IDS)
    expected["attendance_reply_types"] = (1, 2, 3, 4, 5) + LEGACY_IDS[
        "attendance_reply_types"
    ]
    expected["games"] = MOBILE_FIXTURE_IDS + LEGACY_IDS["games"]
    expected["people"] = MOBILE_FIXTURE_IDS + LEGACY_IDS["people"]
    expected["auth_identities"] = MOBILE_FIXTURE_IDS
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
        - {"people", "access_audit", "game_attendance_replies"}
        - MOBILE_TABLES
    )
    if any(_ids(connection, table) for table in empty_tables):
        raise StagingContractError("Officer fixture contains unknown rows")
    if not _mobile_history_is_exact(connection):
        raise StagingContractError("Officer fixture mobile history is drifted")

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
                            "Mobile principal inventory requires exact revision 0005"
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
                                "AND s.auth_identity_id=-112001 "
                                "AND i.status='linked' AND i.person_id=-112001) "
                                "AS expected_tuple, "
                                "count(*) FILTER (WHERE s.status='active' "
                                "AND s.person_id=-112001 AND ("
                                "s.auth_identity_id=-112001 "
                                "AND i.status='linked' AND i.person_id=-112001) "
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
    allowed_states = (
        {"baseline", "restored"} if transition == "grant" else {"granted"}
    )
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


def _database_state(connection) -> dict:
    schema_exists = connection.scalar(
        text("SELECT to_regnamespace('ntubtob') IS NOT NULL")
    )
    if not schema_exists:
        return {
            "revision": None,
            "database_state": "empty",
            "fixture_state": "clean",
        }
    tables = tuple(
        connection.scalars(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='ntubtob' ORDER BY table_name"
            )
        )
    )
    if set(tables) != EXPECTED_TABLES:
        raise StagingContractError(
            "Remote staging schema is partial or drifted; do not retry"
        )
    revisions = tuple(
        connection.scalars(text("SELECT version_num FROM ntubtob.alembic_version"))
    )
    if revisions != (REVISION,):
        raise StagingContractError(
            "Remote staging revision is partial or drifted; do not retry"
        )
    return {
        "revision": REVISION,
        "database_state": "ready",
        "fixture_state": _fixture_state(connection),
    }


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
    expected["auth_identities"] = mobile_ids
    expected["person_qualifications"] = mobile_ids + (1,)
    for table, ids in expected.items():
        if _ids(connection, table) != ids:
            raise StagingContractError(
                f"Remote staging fixture table is drifted: {table}; do not retry"
            )
    empty_tables = (
        (LEGACY_TABLES | PORTAL_TABLES | MOBILE_TABLES) - set(expected) - {"people"}
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


def recover(approval: dict, database_url: str) -> dict:
    state = inventory(approval, database_url)
    if state["database_state"] == "empty":
        outcome = "not_started"
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
    try:
        if before["outcome"] == "not_started":
            _bootstrap_empty_database(engine, root)
            migrated = inventory(approval, database_url)
            if migrated["revision"] != REVISION or migrated["fixture_state"] != "clean":
                raise StagingContractError("Remote staging migration postcheck failed")
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
