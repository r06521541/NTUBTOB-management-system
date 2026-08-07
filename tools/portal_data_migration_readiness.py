from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "docs" / "operations" / "sql" / "portal-data-0001-to-0003.sql"
CHECKSUM = ARTIFACT.with_suffix(".sql.sha256")
LOCAL_OFFLINE_URL = (
    "postgresql+psycopg2://portal_local:local-only-password@"
    "127.0.0.1:55432/ntubtob_portal_local"
)
EXPECTED_REVISIONS = (
    "0001_legacy_baseline",
    "0002_portal_data_foundation",
    "0003_legacy_bigint_activity_game",
)
EXPECTED_TABLES = {
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
    "people",
    "person_qualifications",
}
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
HEADER = """-- GENERATED FILE: do not edit by hand.
-- Source: Alembic 0001_legacy_baseline -> 0003_legacy_bigint_activity_game.
-- REVIEW ARTIFACT ONLY. DO NOT RUN WITHOUT OWNER APPROVAL.
-- This file contains expand-only schema DDL and Alembic version bookkeeping.

"""


class VerificationError(RuntimeError):
    pass


def _config(output_buffer: io.StringIO | None = None) -> Config:
    config = Config(str(ROOT / "alembic.ini"), output_buffer=output_buffer)
    config.set_main_option("sqlalchemy.url", LOCAL_OFFLINE_URL)
    return config


def revision_chain() -> tuple[str, ...]:
    script = ScriptDirectory.from_config(_config())
    revisions = list(script.walk_revisions(base="base", head="heads"))
    return tuple(revision.revision for revision in reversed(revisions))


def render_sql() -> str:
    output = io.StringIO()
    config = _config(output)
    previous_url = os.environ.get("PORTAL_DATA_DATABASE_URL")
    os.environ["PORTAL_DATA_DATABASE_URL"] = LOCAL_OFFLINE_URL
    try:
        command.upgrade(
            config,
            "0001_legacy_baseline:0003_legacy_bigint_activity_game",
            sql=True,
        )
    finally:
        if previous_url is None:
            os.environ.pop("PORTAL_DATA_DATABASE_URL", None)
        else:
            os.environ["PORTAL_DATA_DATABASE_URL"] = previous_url
    rendered = output.getvalue().replace("\r\n", "\n").strip() + "\n"
    rendered = rendered.replace(
        "BEGIN;\n",
        "BEGIN;\n\nSET LOCAL lock_timeout = '5s';\n"
        "SET LOCAL statement_timeout = '60s';\n",
        1,
    )
    return HEADER + rendered


def checksum_for(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _fail(errors: list[str], message: str) -> None:
    errors.append(message)


def verify_sql(sql: str, expected_checksum: str | None = None) -> None:
    errors: list[str] = []
    upper = sql.upper()

    if revision_chain() != EXPECTED_REVISIONS:
        _fail(errors, f"unexpected revision graph: {revision_chain()!r}")
    if not sql.startswith(HEADER):
        _fail(errors, "required generated-file and approval warning header is missing")
    if "BEGIN;" not in upper or not upper.rstrip().endswith("COMMIT;"):
        _fail(errors, "artifact must have one explicit transaction boundary")
    if upper.count("BEGIN;") != 1 or upper.count("COMMIT;") != 1:
        _fail(errors, "artifact must contain exactly one BEGIN and COMMIT")
    if "SET LOCAL LOCK_TIMEOUT = '5S';" not in upper:
        _fail(errors, "bounded transaction-local lock_timeout is missing")
    if "SET LOCAL STATEMENT_TIMEOUT = '60S';" not in upper:
        _fail(errors, "bounded transaction-local statement_timeout is missing")

    for forbidden in ("DROP", "TRUNCATE", "DELETE", "INSERT", "COPY"):
        if re.search(rf"^\s*{forbidden}\b", sql, flags=re.IGNORECASE | re.MULTILINE):
            _fail(errors, f"forbidden SQL token: {forbidden}")
    for remote_pattern in (
        r"postgres(?:ql)?://",
        r"supabase",
        r"amazonaws\.com",
        r"cloudsql",
        r"password\s*=",
    ):
        if re.search(remote_pattern, sql, flags=re.IGNORECASE):
            _fail(errors, f"remote or credential pattern found: {remote_pattern}")

    created_tables = set(
        re.findall(r"CREATE TABLE ntubtob\.([a-z_]+)", sql, flags=re.IGNORECASE)
    )
    if created_tables != EXPECTED_TABLES:
        _fail(errors, f"unexpected created tables: {sorted(created_tables)}")
    if created_tables & LEGACY_TABLES:
        _fail(errors, "artifact attempts to create a catalog-owned legacy table")

    alters = re.findall(
        r"ALTER TABLE ntubtob\.([a-z_]+)\s+(.+?);",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    allowed_alters = {
        ("members", "add column person_id bigint null"),
        (
            "members",
            "add constraint uq_members_person_id unique (person_id)",
        ),
        (
            "members",
            "add constraint fk_members_person foreign key (person_id) references ntubtob.people(id) on delete restrict",
        ),
        (
            "activities",
            "alter column game_id type bigint using game_id::bigint",
        ),
    }
    normalized_alters = {
        (table.lower(), " ".join(body.lower().split())) for table, body in alters
    }
    if normalized_alters != allowed_alters:
        _fail(errors, f"unexpected ALTER TABLE statements: {sorted(normalized_alters)}")

    updates = re.findall(r"^UPDATE\s+([^;]+);", sql, flags=re.IGNORECASE | re.MULTILINE)
    if len(updates) != 2 or any(
        not update.lower().startswith("ntubtob.alembic_version set version_num=")
        for update in updates
    ):
        _fail(errors, "only the two expected Alembic version updates are allowed")

    if expected_checksum is not None and checksum_for(sql) != expected_checksum.strip():
        _fail(errors, "artifact checksum does not match its reviewed sidecar")
    if errors:
        raise VerificationError("; ".join(errors))


def write_artifact() -> None:
    sql = render_sql()
    verify_sql(sql)
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(sql, encoding="utf-8", newline="\n")
    CHECKSUM.write_text(f"{checksum_for(sql)}  {ARTIFACT.name}\n", encoding="ascii")


def verify_artifact() -> None:
    sql = ARTIFACT.read_text(encoding="utf-8")
    checksum_line = CHECKSUM.read_text(encoding="ascii").strip()
    checksum, separator, filename = checksum_line.partition("  ")
    if not separator or filename != ARTIFACT.name:
        raise VerificationError("checksum sidecar format or filename is invalid")
    verify_sql(sql, checksum)
    if sql != render_sql():
        raise VerificationError("artifact differs from current Alembic sources")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render or verify the local-only portal-data SQL review artifact."
    )
    parser.add_argument("action", choices=("render", "verify"))
    args = parser.parse_args()
    if args.action == "render":
        write_artifact()
        print(f"rendered {ARTIFACT.relative_to(ROOT)}")
    else:
        verify_artifact()
        print("portal-data migration artifact verified")


if __name__ == "__main__":
    main()
