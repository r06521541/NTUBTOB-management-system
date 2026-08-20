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


def _officer_audit(connection, transition: str) -> bool:
    expected = OFFICER_AUDITS[transition]
    row = (
        connection.execute(
            text(
                "SELECT id, action, actor_person_id, target_person_id, "
                "auth_identity_id, before_state, after_state, reason, request_id "
                "FROM ntubtob.access_audit WHERE id=:id"
            ),
            {"id": OFFICER_AUDIT_IDS[transition]},
        )
        .mappings()
        .one_or_none()
    )
    return row == {
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
            1,
            "SELECT count(*) FROM ntubtob.mobile_sessions "
            "WHERE auth_identity_id=-112001 AND person_id=-112001",
        ),
        (
            "mobile_refresh_tokens",
            8,
            "SELECT count(*) FROM ntubtob.mobile_refresh_tokens t "
            "JOIN ntubtob.mobile_sessions s ON s.id=t.session_id "
            "WHERE s.auth_identity_id=-112001 AND s.person_id=-112001",
        ),
        (
            "mobile_refresh_attempts",
            7,
            "SELECT count(*) FROM ntubtob.mobile_refresh_attempts a "
            "JOIN ntubtob.mobile_sessions s ON s.id=a.session_id "
            "WHERE s.auth_identity_id=-112001 AND s.person_id=-112001",
        ),
        (
            "mobile_auth_exchanges",
            1,
            "SELECT count(*) FROM ntubtob.mobile_auth_exchanges e "
            "JOIN ntubtob.mobile_sessions s ON s.id=e.session_id "
            "WHERE e.provider='line' AND s.auth_identity_id=-112001 "
            "AND s.person_id=-112001",
        ),
        (
            "mobile_idempotency_records",
            2,
            "SELECT count(*) FROM ntubtob.mobile_idempotency_records i "
            "JOIN ntubtob.mobile_sessions s ON s.id=i.session_id "
            "WHERE i.person_id=-112001 AND s.auth_identity_id=-112001 "
            "AND s.person_id=-112001",
        ),
    )
    for table, expected, owned_query in checks:
        if connection.scalar(text(f"SELECT count(*) FROM ntubtob.{table}")) != expected:
            return False
        if connection.scalar(text(owned_query)) != expected:
            return False
    return True


def _runtime_residue_is_exact(connection) -> bool:
    rows = connection.execute(
        text(
            "SELECT id, game_id, user_id, member_id, person_id, reply, updated_at "
            "FROM ntubtob.game_attendance_replies "
            "WHERE id IN (-112003, -112002, -112001, 3, 4) ORDER BY id"
        )
    ).all()
    return [tuple(row) for row in rows] == list(
        CANONICAL_FIXTURE_REPLY_ROWS + RUNTIME_RESIDUE_ROWS
    )


def _officer_fixture_state(
    connection, private_subject: str, allow_runtime_residue: bool = False
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
    expected["game_attendance_replies"] = (
        MOBILE_FIXTURE_IDS + LEGACY_IDS["game_attendance_replies"]
    )
    expected["people"] = MOBILE_FIXTURE_IDS + LEGACY_IDS["people"]
    expected["auth_identities"] = MOBILE_FIXTURE_IDS
    expected["person_qualifications"] = MOBILE_FIXTURE_IDS + (1,)
    # access_audit is deliberately classified below: its task-owned records are
    # append-only and are the only legitimate difference from the seed fixture.
    expected.pop("access_audit")
    residue_present = False
    residue_ids = MOBILE_FIXTURE_IDS + (3, 4) + LEGACY_IDS["game_attendance_replies"]
    for table, ids in expected.items():
        if (
            table == "game_attendance_replies"
            and _ids(connection, table) == residue_ids
        ):
            if not allow_runtime_residue or not _runtime_residue_is_exact(connection):
                raise StagingContractError("Officer fixture attendance is drifted")
            residue_present = True
            continue
        if _ids(connection, table) != ids:
            raise StagingContractError("Officer fixture is partial or drifted")
    empty_tables = (
        (LEGACY_TABLES | PORTAL_TABLES | MOBILE_TABLES)
        - set(expected)
        - {"people", "access_audit"}
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

    audit_ids = _ids(connection, "access_audit")
    level_version = (tester["portal_access_level"], tester["version"])
    if not _legacy_fixture_audit(connection):
        raise StagingContractError("Officer fixture audit or version is drifted")
    if (
        residue_present
        and level_version == ("basic", 1)
        and audit_ids == LEGACY_IDS["access_audit"]
    ):
        return "runtime_residue"
    if level_version == ("basic", 1) and audit_ids == LEGACY_IDS["access_audit"]:
        return "baseline"
    if (
        level_version == ("officer", 2)
        and audit_ids == (OFFICER_AUDIT_IDS["grant"],) + LEGACY_IDS["access_audit"]
    ):
        if _officer_audit(connection, "grant"):
            return "granted"
    if (
        level_version == ("basic", 3)
        and audit_ids
        == (
            OFFICER_AUDIT_IDS["restore"],
            OFFICER_AUDIT_IDS["grant"],
        )
        + LEGACY_IDS["access_audit"]
    ):
        if _officer_audit(connection, "grant") and _officer_audit(
            connection, "restore"
        ):
            return "restored"
    raise StagingContractError("Officer fixture audit or version is drifted")


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


def _write_officer_transition(connection, transition: str) -> None:
    before, after, expected_version = (
        ("basic", "officer", 1) if transition == "grant" else ("officer", "basic", 2)
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
    audit = OFFICER_AUDITS[transition]
    connection.execute(
        text(
            "INSERT INTO ntubtob.access_audit "
            "(id, action, actor_person_id, target_person_id, auth_identity_id, "
            "before_state, after_state, reason, request_id, created_at) VALUES "
            "(:id, 'access_changed', NULL, :target, :identity, "
            "CAST(:before_state AS json), CAST(:after_state AS json), :reason, "
            ":request_id, timezone('utc', now()))"
        ),
        {
            "id": OFFICER_AUDIT_IDS[transition],
            "target": OFFICER_PERSON_ID,
            "identity": OFFICER_IDENTITY_ID,
            "before_state": json.dumps(audit["before"], sort_keys=True),
            "after_state": json.dumps(audit["after"], sort_keys=True),
            "reason": audit["reason"],
            "request_id": OFFICER_REQUEST_IDS[transition],
        },
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
    allowed_state = "baseline" if transition == "grant" else "granted"
    if before["state"] != allowed_state:
        raise StagingContractError("Remote Officer transition state is not exact")
    engine = create_engine(database_url)
    try:
        try:
            with engine.begin() as connection:
                if _officer_fixture_state(connection, private_subject) != allowed_state:
                    raise StagingContractError(
                        "Remote Officer transition changed before mutation"
                    )
                _write_officer_transition(connection, transition)
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
    parser.add_argument("--inspect-officer", action="store_true")
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
                args.inspect_officer,
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
