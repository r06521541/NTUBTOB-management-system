"""Seed/reset the deterministic fictional Portal UI fixture on localhost only."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tools.portal_data_local_preview import (
    REPOSITORY_OTHER_TABLES,
    REQUIRED_REVISION,
    _is_repository_fixture,
    _replace_repository_fixture,
)

DEMO_MIN_ID = 7101
DEMO_MAX_ID = 7118
DEMO_GAME_MIN_ID = 9710
DEMO_GAME_MAX_ID = 9713
DEMO_SUBJECT_PREFIX = "task099-fictional-"
DEMO_ACCESS_REASON = "TASK-099 fictional access rehearsal"

SEED_SQL = """
DELETE FROM ntubtob.attendance_reply_types;
INSERT INTO ntubtob.attendance_reply_types (id, description) VALUES
  (1, '出席'), (2, '不出席'), (3, '晚到'), (4, '早退'), (5, '未回覆');

INSERT INTO ntubtob.people
  (id, display_name, formal_name, portal_access_level, portal_status, version,
   created_at, updated_at)
SELECT id,
  CASE id WHEN 7101 THEN '虛構管理者' WHEN 7102 THEN '虛構幹部'
    WHEN 7103 THEN '虛構一般隊員' WHEN 7118 THEN '虛構來賓'
    ELSE '虛構球員 ' || (id - 7103)::text END,
  CASE id WHEN 7101 THEN '虛構管理者' WHEN 7102 THEN '虛構幹部'
    WHEN 7103 THEN '虛構一般隊員' WHEN 7118 THEN '虛構來賓'
    ELSE '虛構球員 ' || (id - 7103)::text END,
  CASE id WHEN 7101 THEN 'admin' WHEN 7102 THEN 'officer' ELSE 'basic' END,
  'active', 1, '2037-01-01 00:00:00+00', '2037-01-01 00:00:00+00'
FROM generate_series(7101, 7118) AS id;

INSERT INTO ntubtob.members
  (id, name, enroll_year, major, number, positions, person_id)
SELECT id, (SELECT formal_name FROM ntubtob.people WHERE people.id = ids.id),
  126, '虛構球隊', id - 7100,
  CASE WHEN id IN (7101, 7102) THEN 'Coach' ELSE 'Utility' END, id
FROM generate_series(7101, 7117) AS ids(id);

INSERT INTO ntubtob.auth_identities
  (provider, provider_subject, person_id, status, created_at, updated_at)
VALUES
  ('line', 'task099-fictional-admin', 7101, 'linked', '2037-01-01', '2037-01-01'),
  ('line', 'task099-fictional-officer', 7102, 'linked', '2037-01-01', '2037-01-01'),
  ('line', 'task099-fictional-basic', 7103, 'linked', '2037-01-01', '2037-01-01');

INSERT INTO ntubtob.person_qualifications
  (person_id, qualification, status, valid_from, valid_until,
   granted_by_person_id, reason, created_at, updated_at)
SELECT id, 'team_player', 'active', NULL, NULL, 7101,
  'TASK-099 fictional fixture', '2037-01-01', '2037-01-01'
FROM generate_series(7104, 7117) AS id;
INSERT INTO ntubtob.person_qualifications
  (person_id, qualification, status, valid_from, valid_until,
   granted_by_person_id, reason, created_at, updated_at)
VALUES
  (7101, 'staff', 'active', NULL, NULL, 7101, 'TASK-099 fictional fixture', '2037-01-01', '2037-01-01'),
  (7102, 'staff', 'active', NULL, NULL, 7101, 'TASK-099 fictional fixture', '2037-01-01', '2037-01-01'),
  (7118, 'guest_player', 'active', '2036-01-01', '2038-01-01', 7101, 'TASK-099 fictional fixture', '2037-01-01', '2037-01-01');

INSERT INTO ntubtob.games
  (id, year, season, start_datetime, duration, location, home_team, away_team,
   invitation_time, cancellation_time, cancellation_announcement_time)
VALUES
  (9710, 126, 1, :anchor + interval '3 days', 180, '虛構球場', 'NTUBTOB', '虛構未來隊', :anchor - interval '2 days', NULL, NULL),
  (9711, 126, 1, :anchor + interval '21 days', 180, '虛構球場', '虛構主隊', 'NTUBTOB', :anchor - interval '1 day', NULL, NULL),
  (9712, 126, 1, :anchor - interval '14 days', 180, '虛構球場', 'NTUBTOB', '虛構過去隊', :anchor - interval '30 days', NULL, NULL),
  (9713, 126, 1, :anchor + interval '35 days', 180, '虛構球場', 'NTUBTOB', '虛構取消隊', :anchor - interval '3 days', :anchor - interval '1 day', :anchor - interval '1 day');

INSERT INTO ntubtob.line_users
  (id, nickname, line_user_id, member_id, has_replied, ignored)
SELECT id + 2800, (SELECT display_name FROM ntubtob.people WHERE people.id = ids.id),
  'task099-fictional-line-' || id::text, CASE WHEN id = 7118 THEN NULL ELSE id END,
  id <= 7115, false
FROM generate_series(7104, 7118) AS ids(id);

INSERT INTO ntubtob.game_attendance_replies
  (id, game_id, user_id, member_id, person_id, reply, updated_at)
SELECT id + 2900, 9710, id + 2800, CASE WHEN id = 7118 THEN NULL ELSE id END, id,
  CASE id % 4 WHEN 0 THEN 1 WHEN 1 THEN 2 WHEN 2 THEN 3 ELSE 4 END,
  '2037-01-02 00:00:00+00'
FROM generate_series(7104, 7115) AS ids(id);

INSERT INTO ntubtob.access_audit
  (action, actor_person_id, target_person_id, auth_identity_id, before_state,
   after_state, reason, request_id, created_at)
VALUES ('access_changed', 7101, 7102, NULL, '{"access_level":"officer"}',
  '{"access_level":"officer","fixture":"TASK-099"}',
  'TASK-099 fictional fixture', 'task099-demo-seed', '2037-01-01');
"""


def _count(session: Session, table: str, where: str = "TRUE") -> int:
    return int(
        session.scalar(text(f"SELECT count(*) FROM ntubtob.{table} WHERE {where}"))
    )


def _required_anchor(value: str | datetime | None) -> datetime:
    if isinstance(value, str):
        if not value.isascii() or not 1 <= len(value) <= 40:
            raise RuntimeError("fictional demo anchor must be bounded ISO-8601")
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise RuntimeError(
                "fictional demo anchor must be valid ISO-8601"
            ) from error
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RuntimeError("fictional demo anchor must include a timezone")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _has_exact_demo_audit(session: Session) -> bool:
    invalid = _count(
        session,
        "access_audit",
        f"""
        (request_id = 'task099-demo-seed' AND NOT (
          action = 'access_changed' AND actor_person_id = 7101
          AND target_person_id = 7102 AND auth_identity_id IS NULL
          AND before_state::jsonb = '{{"access_level":"officer"}}'::jsonb
          AND after_state::jsonb = '{{"access_level":"officer","fixture":"TASK-099"}}'::jsonb
          AND reason = 'TASK-099 fictional fixture'
        )) OR
        (request_id <> 'task099-demo-seed' AND NOT (
          action = 'access_changed' AND actor_person_id = 7101
          AND target_person_id BETWEEN 7102 AND 7118 AND auth_identity_id IS NULL
          AND reason = '{DEMO_ACCESS_REASON}'
          AND request_id = 'person-access-' || target_person_id::text || '-'
            || ((after_state::jsonb)->>'access_level')
          AND (
            (target_person_id = 7102
             AND before_state::jsonb = '{{"access_level":"officer"}}'::jsonb
             AND after_state::jsonb = '{{"access_level":"basic"}}'::jsonb)
            OR
            (target_person_id BETWEEN 7103 AND 7118
             AND before_state::jsonb = '{{"access_level":"basic"}}'::jsonb
             AND after_state::jsonb = '{{"access_level":"officer"}}'::jsonb)
          )
        ))
        """,
    )
    duplicate_target = session.scalar(
        text(
            """
            SELECT count(*) FROM (
              SELECT target_person_id FROM ntubtob.access_audit
              WHERE request_id <> 'task099-demo-seed'
              GROUP BY target_person_id HAVING count(*) <> 1
            ) AS duplicate
            """
        )
    )
    inconsistent_person = session.scalar(
        text(
            """
            SELECT count(*) FROM ntubtob.people p
            WHERE p.id BETWEEN 7101 AND 7118 AND (
              (p.id = 7101 AND (p.portal_access_level <> 'admin' OR p.version <> 1))
              OR (p.id = 7102 AND (
                p.portal_access_level <> CASE WHEN EXISTS (
                  SELECT 1 FROM ntubtob.access_audit a
                  WHERE a.target_person_id = p.id AND a.request_id <> 'task099-demo-seed'
                ) THEN 'basic' ELSE 'officer' END
                OR p.version <> 1 + (SELECT count(*) FROM ntubtob.access_audit a
                  WHERE a.target_person_id = p.id AND a.request_id <> 'task099-demo-seed')
              ))
              OR (p.id BETWEEN 7103 AND 7118 AND (
                p.portal_access_level <> CASE WHEN EXISTS (
                  SELECT 1 FROM ntubtob.access_audit a
                  WHERE a.target_person_id = p.id AND a.request_id <> 'task099-demo-seed'
                ) THEN 'officer' ELSE 'basic' END
                OR p.version <> 1 + (SELECT count(*) FROM ntubtob.access_audit a
                  WHERE a.target_person_id = p.id AND a.request_id <> 'task099-demo-seed')
              ))
            )
            """
        )
    )
    return invalid == 0 and duplicate_target == 0 and inconsistent_person == 0


def _is_demo_fixture(session: Session) -> bool:
    marker = _count(
        session,
        "access_audit",
        "request_id = 'task099-demo-seed'",
    )
    if marker != 1:
        return False
    expected_counts = {
        "people": 18,
        "members": 17,
        "auth_identities": 3,
        "person_qualifications": 17,
        "games": 4,
        "line_users": 15,
        "game_attendance_replies": 12,
    }
    if any(_count(session, table) != count for table, count in expected_counts.items()):
        return False
    bounded = {
        "people": f"id BETWEEN {DEMO_MIN_ID} AND {DEMO_MAX_ID}",
        "members": f"id BETWEEN {DEMO_MIN_ID} AND {DEMO_MAX_ID}",
        "auth_identities": f"provider_subject LIKE '{DEMO_SUBJECT_PREFIX}%'",
        "person_qualifications": f"person_id BETWEEN {DEMO_MIN_ID} AND {DEMO_MAX_ID}",
        "games": f"id BETWEEN {DEMO_GAME_MIN_ID} AND {DEMO_GAME_MAX_ID}",
        "line_users": "line_user_id LIKE 'task099-fictional-line-%'",
        "game_attendance_replies": f"game_id BETWEEN {DEMO_GAME_MIN_ID} AND {DEMO_GAME_MAX_ID}",
    }
    if not all(
        _count(session, table, f"NOT ({where})") == 0
        for table, where in bounded.items()
    ):
        return False
    if _count(session, "identity_review_threads") or _count(
        session, "identity_review_messages"
    ):
        return False
    if _count(session, "ballparks") or any(
        _count(session, table)
        for table in REPOSITORY_OTHER_TABLES
        if table not in {"identity_review_threads", "identity_review_messages"}
    ):
        return False
    return (
        _has_exact_demo_audit(session)
        and _count(
            session,
            "access_audit",
            "actor_person_id IS NOT NULL AND actor_person_id NOT BETWEEN 7101 AND 7118",
        )
        == 0
        and _count(
            session,
            "access_audit",
            "target_person_id IS NOT NULL AND target_person_id NOT BETWEEN 7101 AND 7118",
        )
        == 0
        and _count(
            session,
            "access_audit",
            "request_id <> 'task099-demo-seed' AND request_id NOT LIKE 'person-access-%'",
        )
        == 0
    )


def operate(
    command: str,
    database_url: str,
    anchor: str | datetime | None = None,
    engine_factory=create_engine,
) -> None:
    anchor_value = _required_anchor(anchor) if command in {"seed", "reset"} else None
    safe_url = require_local_database_url(database_url)
    engine = engine_factory(safe_url)
    try:
        with Session(engine) as session, session.begin():
            revision = session.scalar(
                text("SELECT version_num FROM ntubtob.alembic_version")
            )
            if revision != REQUIRED_REVISION:
                raise RuntimeError("fictional demo requires database revision 0004")
            repository_fixture = _is_repository_fixture(session)
            demo_fixture = _is_demo_fixture(session)
            if not repository_fixture and not demo_fixture:
                raise RuntimeError(
                    "database is not the repository or TASK-099 demo fixture"
                )
            _replace_repository_fixture(session)
            session.execute(text("DELETE FROM ntubtob.attendance_reply_types"))
            if command in {"seed", "reset"}:
                session.execute(text(SEED_SQL), {"anchor": anchor_value})
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Operate the TASK-099 fictional UI demo"
    )
    parser.add_argument("command", choices=("seed", "reset", "cleanup"))
    parser.add_argument("--confirm-fictional-demo", action="store_true")
    parser.add_argument("--anchor")
    args = parser.parse_args(argv)
    if not args.confirm_fictional_demo:
        raise RuntimeError("--confirm-fictional-demo is required")
    if args.command == "cleanup" and args.anchor is not None:
        raise RuntimeError("cleanup does not accept --anchor")
    operate(
        args.command,
        os.environ.get("PORTAL_DATA_DATABASE_URL", ""),
        anchor=args.anchor,
    )
    print(f"fictional demo {args.command} complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
