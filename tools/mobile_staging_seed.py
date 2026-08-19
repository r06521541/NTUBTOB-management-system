"""Deterministic fictional mobile staging rehearsal for local PostgreSQL only."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import Engine, create_engine, text

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)

REVISION = "0005_mobile_auth_api_foundation"
PERSON_IDS = (-112001, -112002, -112003)
IDENTITY_IDS = (-112001, -112002, -112003)
QUALIFICATION_IDS = (-112001, -112002, -112003)
GAME_IDS = (-112001, -112002, -112003)
REPLY_IDS = (-112001, -112002, -112003)
REPLY_TYPES = {
    1: "attending",
    2: "not_attending",
    3: "arriving_late",
    4: "leaving_early",
    5: "undecided",
}
FIXTURE_REPLY_TYPES = {
    key: f"TASK112 fixture {value}" for key, value in REPLY_TYPES.items()
}
ANCHOR = datetime(2035, 1, 10, 10, tzinfo=timezone.utc)
FIXTURE_REPLY_AT = datetime(2000, 1, 1, tzinfo=timezone.utc)
LEGACY_FIXTURE_REPLY_AT = ANCHOR
HIDDEN_TEST_REPLY_IDS = (1, 2)


class StagingSeedError(RuntimeError):
    pass


def _validate_subject(value: str) -> str:
    if not isinstance(value, str) or not 8 <= len(value) <= 255 or value.isspace():
        raise StagingSeedError("Private tester input is invalid")
    return value


def _counts(connection) -> dict[str, int]:
    return {
        "people": connection.scalar(
            text("SELECT count(*) FROM ntubtob.people WHERE id = ANY(:ids)"),
            {"ids": list(PERSON_IDS)},
        ),
        "identities": connection.scalar(
            text("SELECT count(*) FROM ntubtob.auth_identities WHERE id = ANY(:ids)"),
            {"ids": list(IDENTITY_IDS)},
        ),
        "qualifications": connection.scalar(
            text(
                "SELECT count(*) FROM ntubtob.person_qualifications WHERE id = ANY(:ids)"
            ),
            {"ids": list(QUALIFICATION_IDS)},
        ),
        "games": connection.scalar(
            text("SELECT count(*) FROM ntubtob.games WHERE id = ANY(:ids)"),
            {"ids": list(GAME_IDS)},
        ),
        "replies": connection.scalar(
            text(
                "SELECT count(*) FROM ntubtob.game_attendance_replies WHERE id = ANY(:ids)"
            ),
            {"ids": list(REPLY_IDS)},
        ),
    }


def _assert_exact(connection, private_subject: str) -> None:
    expected = {
        "people": 3,
        "identities": 3,
        "qualifications": 3,
        "games": 3,
        "replies": 3,
    }
    if _counts(connection) != expected:
        raise StagingSeedError("Fictional staging fixture is incomplete or drifted")
    _reply_type_ownership(connection)
    tester = connection.execute(
        text(
            "SELECT person_id, status FROM ntubtob.auth_identities WHERE provider='line' AND provider_subject=:subject"
        ),
        {"subject": private_subject},
    ).all()
    if tester != [(-112001, "linked")]:
        raise StagingSeedError("Private tester mapping cardinality is not exactly one")
    drift = connection.scalar(
        text(
            """
        SELECT count(*) FROM ntubtob.people
        WHERE id = ANY(:ids) AND (
          display_name NOT LIKE '虛構 Staging %' OR portal_access_level <> 'basic'
          OR portal_status <> 'active' OR admin_note IS NOT NULL)
        """
        ),
        {"ids": list(PERSON_IDS)},
    )
    if drift:
        raise StagingSeedError("Fictional staging fixture content drifted")


def seed(engine: Engine, private_subject: str) -> dict[str, int]:
    private_subject = _validate_subject(private_subject)
    with engine.begin() as connection:
        revision = connection.scalar(
            text("SELECT version_num FROM ntubtob.alembic_version")
        )
        if revision != REVISION:
            raise StagingSeedError("Database revision must be exact 0005")
        counts = _counts(connection)
        if any(counts.values()):
            _assert_exact(connection, private_subject)
            return {**counts, "tester_mappings": 1, "reused": 1}
        collision = connection.scalar(
            text(
                "SELECT count(*) FROM ntubtob.auth_identities WHERE provider='line' AND provider_subject=:subject"
            ),
            {"subject": private_subject},
        )
        if collision:
            raise StagingSeedError(
                "Private tester identity is already linked outside fixture"
            )
        ownership = _reply_type_ownership(connection, allow_missing=True)
        if ownership == "missing":
            connection.execute(
                text(
                    "INSERT INTO ntubtob.attendance_reply_types (id, description) "
                    "VALUES (:id, :description)"
                ),
                [
                    {"id": key, "description": value}
                    for key, value in FIXTURE_REPLY_TYPES.items()
                ],
            )
        connection.execute(
            text(
                """
          INSERT INTO ntubtob.people
            (id, display_name, formal_name, admin_note, portal_access_level, portal_status, version, created_at, updated_at)
          VALUES
            (-112001, '虛構 Staging 測試員', NULL, NULL, 'basic', 'active', 1, :now, :now),
            (-112002, '虛構 Staging 隊友甲', NULL, NULL, 'basic', 'active', 1, :now, :now),
            (-112003, '虛構 Staging 隊友乙', NULL, NULL, 'basic', 'active', 1, :now, :now)
        """
            ),
            {"now": ANCHOR},
        )
        connection.execute(
            text(
                """
          INSERT INTO ntubtob.person_qualifications
            (id, person_id, qualification, status, valid_from, valid_until, granted_by_person_id, reason, created_at, updated_at)
          VALUES
            (-112001, -112001, 'guest_player', 'active', :start, :finish, NULL, 'fictional staging', :now, :now),
            (-112002, -112002, 'guest_player', 'active', :start, :finish, NULL, 'fictional staging', :now, :now),
            (-112003, -112003, 'guest_player', 'active', :start, :finish, NULL, 'fictional staging', :now, :now)
        """
            ),
            {
                "start": datetime(2034, 1, 1, tzinfo=timezone.utc),
                "finish": datetime(2038, 1, 1, tzinfo=timezone.utc),
                "now": ANCHOR,
            },
        )
        connection.execute(
            text(
                """
          INSERT INTO ntubtob.auth_identities
            (id, provider, provider_subject, person_id, status, created_at, updated_at)
          VALUES
            (-112001, 'line', :subject, -112001, 'linked', :now, :now),
            (-112002, 'line', 'task112-fictional-teammate-a', -112002, 'linked', :now, :now),
            (-112003, 'line', 'task112-fictional-teammate-b', -112003, 'linked', :now, :now)
        """
            ),
            {"subject": private_subject, "now": ANCHOR},
        )
        connection.execute(
            text(
                """
          INSERT INTO ntubtob.games
            (id, year, season, start_datetime, duration, location, home_team, away_team, invitation_time, cancellation_time, cancellation_announcement_time)
          VALUES
            (-112001, 2035, 1, '2035-02-01T02:00:00Z', 150, '虛構球場 A', '台大OB', '虛構對手甲', :now, NULL, NULL),
            (-112002, 2035, 1, '2035-02-08T03:00:00Z', 150, '虛構球場 B', '虛構對手乙', '台大OB', :now, NULL, NULL),
            (-112003, 2035, 1, '2035-02-15T04:00:00Z', 150, '虛構球場 C', '台大OB', '虛構對手丙', :now, NULL, NULL)
        """
            ),
            {"now": ANCHOR},
        )
        connection.execute(
            text(
                """
          INSERT INTO ntubtob.game_attendance_replies
            (id, game_id, user_id, member_id, person_id, reply, updated_at)
          VALUES
            (-112001, -112001, NULL, NULL, -112001, 1, :now),
            (-112002, -112001, NULL, NULL, -112002, 2, :now),
            (-112003, -112002, NULL, NULL, -112003, 5, :now)
        """
            ),
            {"now": FIXTURE_REPLY_AT},
        )
        _assert_exact(connection, private_subject)
        return {**_counts(connection), "tester_mappings": 1, "reused": 0}


def _attendance_repair_state(connection) -> dict[str, object]:
    revision = connection.scalar(
        text("SELECT version_num FROM ntubtob.alembic_version")
    )
    if revision != REVISION:
        raise StagingSeedError("Database revision must be exact 0005")
    fixture_rows = connection.execute(
        text(
            "SELECT id, game_id, user_id, member_id, person_id, reply, updated_at "
            "FROM ntubtob.game_attendance_replies "
            "WHERE id = ANY(:ids) ORDER BY id"
        ),
        {"ids": list(REPLY_IDS)},
    ).all()
    expected = [
        (-112003, -112002, None, None, -112003, 5),
        (-112002, -112001, None, None, -112002, 2),
        (-112001, -112001, None, None, -112001, 1),
    ]
    if [tuple(row[:6]) for row in fixture_rows] != expected:
        raise StagingSeedError("Fictional attendance fixture is drifted")
    timestamps = {row.updated_at for row in fixture_rows}
    hidden_rows = connection.execute(
        text(
            "SELECT id, game_id, user_id, member_id, person_id, reply, updated_at "
            "FROM ntubtob.game_attendance_replies "
            "WHERE person_id=-112001 AND game_id=-112001 "
            "AND id <> -112001 ORDER BY id"
        )
    ).all()
    if timestamps == {FIXTURE_REPLY_AT} and not hidden_rows:
        return {"state": "repaired", "hidden_ids": ()}
    hidden_shape = [tuple(row[1:6]) for row in hidden_rows]
    if (
        timestamps != {LEGACY_FIXTURE_REPLY_AT}
        or tuple(row.id for row in hidden_rows) != HIDDEN_TEST_REPLY_IDS
        or hidden_shape
        != [
            (-112001, None, None, -112001, 5),
            (-112001, None, None, -112001, 5),
        ]
    ):
        raise StagingSeedError("Fictional attendance repair state is drifted")
    if any(
        row.id <= 0
        or row.updated_at is None
        or row.updated_at >= LEGACY_FIXTURE_REPLY_AT
        for row in hidden_rows
    ):
        raise StagingSeedError("Fictional attendance repair state is drifted")
    return {"state": "required", "hidden_ids": tuple(row.id for row in hidden_rows)}


def inspect_attendance_repair(engine: Engine) -> dict[str, object]:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            state = _attendance_repair_state(connection)
        finally:
            transaction.rollback()
    return {"state": state["state"], "hidden_rows": len(state["hidden_ids"])}


def repair_attendance_fixture(engine: Engine) -> dict[str, object]:
    with engine.begin() as connection:
        state = _attendance_repair_state(connection)
        hidden_ids = state["hidden_ids"]
        if state["state"] == "repaired":
            return {"state": "repaired", "removed_hidden_rows": 0}
        deleted = connection.execute(
            text(
                "DELETE FROM ntubtob.game_attendance_replies "
                "WHERE id = ANY(:ids)"
            ),
            {"ids": list(hidden_ids)},
        ).rowcount
        updated = connection.execute(
            text(
                "UPDATE ntubtob.game_attendance_replies SET updated_at=:fixed "
                "WHERE id = ANY(:ids) AND updated_at=:legacy"
            ),
            {
                "ids": list(REPLY_IDS),
                "fixed": FIXTURE_REPLY_AT,
                "legacy": LEGACY_FIXTURE_REPLY_AT,
            },
        ).rowcount
        if deleted != 2 or updated != 3:
            raise StagingSeedError("Fictional attendance repair changed unexpectedly")
        after = _attendance_repair_state(connection)
        if after["state"] != "repaired":
            raise StagingSeedError("Fictional attendance repair postcheck failed")
        return {"state": "repaired", "removed_hidden_rows": deleted}


def cleanup(engine: Engine, private_subject: str) -> dict[str, int]:
    private_subject = _validate_subject(private_subject)
    with engine.begin() as connection:
        counts = _counts(connection)
        if not any(counts.values()):
            return {**counts, "tester_mappings": 0}
        _assert_exact(connection, private_subject)
        for table, ids in (
            ("game_attendance_replies", REPLY_IDS),
            ("auth_identities", IDENTITY_IDS),
            ("person_qualifications", QUALIFICATION_IDS),
            ("games", GAME_IDS),
            ("people", PERSON_IDS),
        ):
            connection.execute(
                text(f"DELETE FROM ntubtob.{table} WHERE id = ANY(:ids)"),
                {"ids": list(ids)},
            )
        if _reply_type_ownership(connection) == "fixture":
            connection.execute(
                text(
                    "DELETE FROM ntubtob.attendance_reply_types " "WHERE id = ANY(:ids)"
                ),
                {"ids": list(REPLY_TYPES)},
            )
        remaining = _counts(connection)
        if any(remaining.values()):
            raise StagingSeedError("Fictional staging cleanup is incomplete")
        return {**remaining, "tester_mappings": 0}


def _reply_type_ownership(connection, allow_missing: bool = False) -> str:
    rows = dict(
        connection.execute(
            text(
                "SELECT id, description FROM ntubtob.attendance_reply_types "
                "WHERE id = ANY(:ids) ORDER BY id"
            ),
            {"ids": list(REPLY_TYPES)},
        ).all()
    )
    if not rows and allow_missing:
        return "missing"
    if rows == REPLY_TYPES:
        return "baseline"
    if rows == FIXTURE_REPLY_TYPES:
        return "fixture"
    raise StagingSeedError(
        "Attendance reply type reference rows are partial or drifted"
    )


def main() -> None:
    database_url = require_local_database_url(
        os.environ.get("PORTAL_DATA_DATABASE_URL")
    )
    subject = os.environ.get("MOBILE_STAGING_PROVIDER_SUBJECT", "")
    action = os.environ.get("MOBILE_STAGING_ACTION", "seed")
    engine = create_engine(database_url)
    try:
        summary = (
            cleanup(engine, subject) if action == "cleanup" else seed(engine, subject)
        )
    finally:
        engine.dispose()
    print(json_safe_summary(action, summary))


def json_safe_summary(action: str, summary: dict[str, int]) -> str:
    values = " ".join(f"{key}={summary[key]}" for key in sorted(summary))
    return f"mobile staging {action} complete: {values}"


if __name__ == "__main__":
    main()
