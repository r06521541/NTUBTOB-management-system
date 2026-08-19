"""Approved remote staging migration/fixture operation; dry-run by default."""

from __future__ import annotations

import argparse
import json
import os
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
    from .mobile_staging_seed import StagingSeedError, seed
    from .setup_portal_data_legacy import LEGACY_FIXTURE_SQL
except ImportError:  # pragma: no cover
    from mobile_staging_contract import (
        REVISION,
        StagingContractError,
        load_approval,
        validate_database_identity,
    )
    from mobile_staging_seed import StagingSeedError, seed
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
EXPECTED_TABLES = LEGACY_TABLES | PORTAL_TABLES | MOBILE_TABLES | {
    "alembic_version"
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
        LEGACY_TABLES | PORTAL_TABLES | MOBILE_TABLES
    ) - set(expected) - {"people"}
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
            if (
                migrated["revision"] != REVISION
                or migrated["fixture_state"] != "clean"
            ):
                raise StagingContractError(
                    "Remote staging migration postcheck failed"
                )
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args(argv)
    try:
        approval = load_approval(args.approval)
        database_url = os.environ.get("MOBILE_STAGING_DATABASE_URL", "")
        if args.recover:
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
