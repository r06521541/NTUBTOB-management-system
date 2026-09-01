"""Read-only, deidentified persistent-admin cutover inventory.

The default command is an offline preflight.  ``--execute`` is reserved for a
later Owner-approved work package; it never mutates schema, authority or data.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

EXPECTED_REVISION = "0012_persistent_admin_authority"
MAX_COUNT = 1_000_000


class InventoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class InventorySnapshot:
    revision: str
    mode: str
    allowlist_presence: str
    allowlist_parse: str
    allowlisted_reachable: int
    persistent_reachable: int
    both: int
    allowlist_only: int
    persistent_only: int


def parse_private_allowlist(value: str | None) -> tuple[int, ...]:
    if value is None or not value.strip():
        return ()
    parts = value.split(",")
    if any(
        not part.strip().isascii() or not part.strip().isdecimal() for part in parts
    ):
        raise InventoryError("allowlist_invalid")
    parsed = tuple(int(part.strip()) for part in parts)
    if any(value <= 0 for value in parsed) or len(parsed) != len(set(parsed)):
        raise InventoryError("allowlist_invalid")
    return parsed


def _bounded_count(value) -> int:
    if type(value) is not int or not 0 <= value <= MAX_COUNT:
        raise InventoryError("count_out_of_bounds")
    return value


def collect_inventory(
    session: Session,
    admin_member_ids: tuple[int, ...],
    *,
    expected_revision: str = EXPECTED_REVISION,
) -> InventorySnapshot:
    session.execute(text("SET TRANSACTION READ ONLY"))
    session.execute(text("SET LOCAL lock_timeout = '5s'"))
    session.execute(text("SET LOCAL statement_timeout = '15s'"))
    revisions = tuple(
        session.scalars(text("SELECT version_num FROM ntubtob.alembic_version"))
    )
    if revisions != (expected_revision,):
        raise InventoryError("revision_mismatch")
    revision = revisions[0]
    state = session.execute(
        text(
            "SELECT mode, epoch FROM ntubtob.portal_authority_state "
            "WHERE singleton_id = 1"
        )
    ).one_or_none()
    if state is None or state.mode not in {"legacy_allowlist", "persistent"}:
        raise InventoryError("authority_state_invalid")
    if type(state.epoch) is not int or state.epoch < 1:
        raise InventoryError("authority_state_invalid")
    counts = session.execute(
        text(
            """
            WITH reachable AS (
              SELECT p.id,
                     COALESCE(
                       bool_or(m.id = ANY(CAST(:member_ids AS bigint[]))), false
                     ) AS allowlisted,
                     (p.portal_access_level = 'admin') AS persistent
                FROM ntubtob.people p
                JOIN ntubtob.auth_identities i
                  ON i.person_id = p.id AND i.status = 'linked'
                LEFT JOIN ntubtob.members m ON m.person_id = p.id
               WHERE p.portal_status = 'active'
               GROUP BY p.id, p.portal_access_level
            )
            SELECT
              count(*) FILTER (WHERE allowlisted),
              count(*) FILTER (WHERE persistent),
              count(*) FILTER (WHERE allowlisted AND persistent),
              count(*) FILTER (WHERE allowlisted AND NOT persistent),
              count(*) FILTER (WHERE persistent AND NOT allowlisted)
              FROM reachable
            """
        ),
        {"member_ids": list(admin_member_ids)},
    ).one()
    return InventorySnapshot(
        revision=revision,
        mode=state.mode,
        allowlist_presence="present" if admin_member_ids else "absent",
        allowlist_parse="valid",
        allowlisted_reachable=_bounded_count(counts[0]),
        persistent_reachable=_bounded_count(counts[1]),
        both=_bounded_count(counts[2]),
        allowlist_only=_bounded_count(counts[3]),
        persistent_only=_bounded_count(counts[4]),
    )


def render_snapshot(snapshot: InventorySnapshot) -> str:
    lines = (
        "persistent_admin_inventory=v1",
        f"revision={snapshot.revision}",
        f"mode={snapshot.mode}",
        f"allowlist_presence={snapshot.allowlist_presence}",
        f"allowlist_parse={snapshot.allowlist_parse}",
        f"allowlisted_reachable={snapshot.allowlisted_reachable}",
        f"persistent_reachable={snapshot.persistent_reachable}",
        f"mapping_both={snapshot.both}",
        f"mapping_allowlist_only={snapshot.allowlist_only}",
        f"mapping_persistent_only={snapshot.persistent_only}",
    )
    output = "\n".join(lines) + "\n"
    if not output.isascii():
        raise InventoryError("output_not_ascii")
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--database-url-env", default="PORTAL_DATA_DATABASE_URL")
    parser.add_argument("--allowlist-env", default="WEB_PORTAL_ADMIN_MEMBER_IDS")
    parser.add_argument("--expected-host-env", default="PERSISTENT_ADMIN_EXPECTED_HOST")
    parser.add_argument("--expected-port-env", default="PERSISTENT_ADMIN_EXPECTED_PORT")
    parser.add_argument(
        "--expected-database-env", default="PERSISTENT_ADMIN_EXPECTED_DATABASE"
    )
    parser.add_argument("--expected-revision", default=EXPECTED_REVISION)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.execute:
        print("persistent_admin_inventory=v1\nstatus=preflight_only")
        return 0
    expected_host = os.environ.get(args.expected_host_env)
    expected_port_raw = os.environ.get(args.expected_port_env)
    expected_database = os.environ.get(args.expected_database_env)
    expected_port = (
        int(expected_port_raw)
        if isinstance(expected_port_raw, str)
        and expected_port_raw.isascii()
        and expected_port_raw.isdecimal()
        else None
    )
    if (
        not expected_host
        or not isinstance(expected_port, int)
        or not 1 <= expected_port <= 65535
        or not expected_database
        or args.expected_revision != EXPECTED_REVISION
    ):
        print("persistent_admin_inventory=v1\nstatus=target_invalid")
        return 2
    database_url = os.environ.get(args.database_url_env)
    engine = None
    try:
        url = make_url(database_url or "")
        if (
            url.host != expected_host
            or (url.port or 5432) != expected_port
            or url.database != expected_database
        ):
            raise InventoryError("target_mismatch")
        allowlist = parse_private_allowlist(os.environ.get(args.allowlist_env))
        engine = create_engine(url)
        with Session(engine) as session, session.begin():
            snapshot = collect_inventory(
                session, allowlist, expected_revision=args.expected_revision
            )
        print(render_snapshot(snapshot), end="")
        return 0
    except Exception:
        print("persistent_admin_inventory=v1\nstatus=inventory_unavailable")
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
