"""Deterministic fictional mobile staging rehearsal for local PostgreSQL only."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import Engine, create_engine, text

from shared_lib.shared_module.portal_data.local_database import \
    require_local_database_url

REVISION = "0005_mobile_auth_api_foundation"
PERSON_IDS = (-112001, -112002, -112003)
IDENTITY_IDS = (-112001, -112002, -112003)
QUALIFICATION_IDS = (-112001, -112002, -112003)
GAME_IDS = (-112001, -112002, -112003)
REPLY_IDS = (-112001, -112002, -112003)
REPLY_TYPE_IDS = (1, 2, 3, 4, 5)
ANCHOR = datetime(2035, 1, 10, 10, tzinfo=timezone.utc)


class StagingSeedError(RuntimeError):
    pass


def _validate_subject(value: str) -> str:
    if not isinstance(value, str) or not 8 <= len(value) <= 255 or value.isspace():
        raise StagingSeedError("Private tester input is invalid")
    return value


def _counts(connection) -> dict[str, int]:
    return {
        "people": connection.scalar(text("SELECT count(*) FROM ntubtob.people WHERE id = ANY(:ids)"), {"ids": list(PERSON_IDS)}),
        "identities": connection.scalar(text("SELECT count(*) FROM ntubtob.auth_identities WHERE id = ANY(:ids)"), {"ids": list(IDENTITY_IDS)}),
        "qualifications": connection.scalar(text("SELECT count(*) FROM ntubtob.person_qualifications WHERE id = ANY(:ids)"), {"ids": list(QUALIFICATION_IDS)}),
        "games": connection.scalar(text("SELECT count(*) FROM ntubtob.games WHERE id = ANY(:ids)"), {"ids": list(GAME_IDS)}),
        "replies": connection.scalar(text("SELECT count(*) FROM ntubtob.game_attendance_replies WHERE id = ANY(:ids)"), {"ids": list(REPLY_IDS)}),
        "reply_types": connection.scalar(text("SELECT count(*) FROM ntubtob.attendance_reply_types WHERE id = ANY(:ids)"), {"ids": list(REPLY_TYPE_IDS)}),
    }


def _assert_exact(connection, private_subject: str) -> None:
    expected = {
        "people": 3,
        "identities": 3,
        "qualifications": 3,
        "games": 3,
        "replies": 3,
        "reply_types": 5,
    }
    if _counts(connection) != expected:
        raise StagingSeedError("Fictional staging fixture is incomplete or drifted")
    tester = connection.execute(
        text("SELECT person_id, status FROM ntubtob.auth_identities WHERE provider='line' AND provider_subject=:subject"),
        {"subject": private_subject},
    ).all()
    if tester != [(-112001, "linked")]:
        raise StagingSeedError("Private tester mapping cardinality is not exactly one")
    drift = connection.scalar(
        text("""
        SELECT count(*) FROM ntubtob.people
        WHERE id = ANY(:ids) AND (
          display_name NOT LIKE '虛構 Staging %' OR portal_access_level <> 'basic'
          OR portal_status <> 'active' OR admin_note IS NOT NULL)
        """),
        {"ids": list(PERSON_IDS)},
    )
    if drift:
        raise StagingSeedError("Fictional staging fixture content drifted")


def seed(engine: Engine, private_subject: str) -> dict[str, int]:
    private_subject = _validate_subject(private_subject)
    with engine.begin() as connection:
        revision = connection.scalar(text("SELECT version_num FROM ntubtob.alembic_version"))
        if revision != REVISION:
            raise StagingSeedError("Database revision must be exact 0005")
        counts = _counts(connection)
        if any(counts.values()):
            _assert_exact(connection, private_subject)
            return {**counts, "tester_mappings": 1, "reused": 1}
        collision = connection.scalar(
            text("SELECT count(*) FROM ntubtob.auth_identities WHERE provider='line' AND provider_subject=:subject"),
            {"subject": private_subject},
        )
        if collision:
            raise StagingSeedError("Private tester identity is already linked outside fixture")
        connection.execute(text("""
          INSERT INTO ntubtob.attendance_reply_types (id, description) VALUES
            (1, 'TASK112 attending'), (2, 'TASK112 not attending'),
            (3, 'TASK112 arriving late'), (4, 'TASK112 leaving early'),
            (5, 'TASK112 undecided')
        """))
        connection.execute(text("""
          INSERT INTO ntubtob.people
            (id, display_name, formal_name, admin_note, portal_access_level, portal_status, version, created_at, updated_at)
          VALUES
            (-112001, '虛構 Staging 測試員', NULL, NULL, 'basic', 'active', 1, :now, :now),
            (-112002, '虛構 Staging 隊友甲', NULL, NULL, 'basic', 'active', 1, :now, :now),
            (-112003, '虛構 Staging 隊友乙', NULL, NULL, 'basic', 'active', 1, :now, :now)
        """), {"now": ANCHOR})
        connection.execute(text("""
          INSERT INTO ntubtob.person_qualifications
            (id, person_id, qualification, status, valid_from, valid_until, granted_by_person_id, reason, created_at, updated_at)
          VALUES
            (-112001, -112001, 'guest_player', 'active', :start, :finish, NULL, 'fictional staging', :now, :now),
            (-112002, -112002, 'guest_player', 'active', :start, :finish, NULL, 'fictional staging', :now, :now),
            (-112003, -112003, 'guest_player', 'active', :start, :finish, NULL, 'fictional staging', :now, :now)
        """), {"start": datetime(2034, 1, 1, tzinfo=timezone.utc), "finish": datetime(2038, 1, 1, tzinfo=timezone.utc), "now": ANCHOR})
        connection.execute(text("""
          INSERT INTO ntubtob.auth_identities
            (id, provider, provider_subject, person_id, status, created_at, updated_at)
          VALUES
            (-112001, 'line', :subject, -112001, 'linked', :now, :now),
            (-112002, 'line', 'task112-fictional-teammate-a', -112002, 'linked', :now, :now),
            (-112003, 'line', 'task112-fictional-teammate-b', -112003, 'linked', :now, :now)
        """), {"subject": private_subject, "now": ANCHOR})
        connection.execute(text("""
          INSERT INTO ntubtob.games
            (id, year, season, start_datetime, duration, location, home_team, away_team, invitation_time, cancellation_time, cancellation_announcement_time)
          VALUES
            (-112001, 2035, 1, '2035-02-01T02:00:00Z', 150, '虛構球場 A', '台大OB', '虛構對手甲', :now, NULL, NULL),
            (-112002, 2035, 1, '2035-02-08T03:00:00Z', 150, '虛構球場 B', '虛構對手乙', '台大OB', :now, NULL, NULL),
            (-112003, 2035, 1, '2035-02-15T04:00:00Z', 150, '虛構球場 C', '台大OB', '虛構對手丙', :now, NULL, NULL)
        """), {"now": ANCHOR})
        connection.execute(text("""
          INSERT INTO ntubtob.game_attendance_replies
            (id, game_id, user_id, member_id, person_id, reply, updated_at)
          VALUES
            (-112001, -112001, NULL, NULL, -112001, 1, :now),
            (-112002, -112001, NULL, NULL, -112002, 2, :now),
            (-112003, -112002, NULL, NULL, -112003, 5, :now)
        """), {"now": ANCHOR})
        _assert_exact(connection, private_subject)
        return {**_counts(connection), "tester_mappings": 1, "reused": 0}


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
        connection.execute(
            text("DELETE FROM ntubtob.attendance_reply_types WHERE id = ANY(:ids)"),
            {"ids": list(REPLY_TYPE_IDS)},
        )
        remaining = _counts(connection)
        if any(remaining.values()):
            raise StagingSeedError("Fictional staging cleanup is incomplete")
        return {**remaining, "tester_mappings": 0}


def main() -> None:
    database_url = require_local_database_url(os.environ.get("PORTAL_DATA_DATABASE_URL"))
    subject = os.environ.get("MOBILE_STAGING_PROVIDER_SUBJECT", "")
    action = os.environ.get("MOBILE_STAGING_ACTION", "seed")
    engine = create_engine(database_url)
    try:
        summary = cleanup(engine, subject) if action == "cleanup" else seed(engine, subject)
    finally:
        engine.dispose()
    print(json_safe_summary(action, summary))


def json_safe_summary(action: str, summary: dict[str, int]) -> str:
    values = " ".join(f"{key}={summary[key]}" for key in sorted(summary))
    return f"mobile staging {action} complete: {values}"


if __name__ == "__main__":
    main()
