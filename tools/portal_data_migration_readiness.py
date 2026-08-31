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
    "0004_phase_c_identity_lifecycle",
    "0005_mobile_auth_api_foundation",
    "0006_staging_broker_operation_journal",
    "0007_mobile_notifications",
    "0008_mobile_notification_delivery",
    "0009_event_management_writes",
    "0010_apple_provider_lifecycle",
    "0011_event_notification_guest_lifecycle",
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
EXPECTED_INDEXES = {
    ("ix_auth_identities_person", "auth_identities"),
    ("ix_event_invitees_event_included", "event_invitees"),
    ("ix_person_qualifications_active", "person_qualifications"),
}
EXPECTED_TRIGGERS = {
    ("access_audit_append_only", "access_audit"),
    ("event_audit_append_only", "event_audit"),
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
-- Source: Alembic base -> 0003_legacy_bigint_activity_game.
-- REVIEW ARTIFACT ONLY. DO NOT RUN WITHOUT OWNER APPROVAL.
-- This file atomically records the reviewed baseline, applies expand-only DDL,
-- and enables fail-closed RLS with zero policies on all new portal-data tables.

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
            "0003_legacy_bigint_activity_game",
            sql=True,
        )
    finally:
        if previous_url is None:
            os.environ.pop("PORTAL_DATA_DATABASE_URL", None)
        else:
            os.environ["PORTAL_DATA_DATABASE_URL"] = previous_url
    rendered = (
        "\n".join(
            line.rstrip()
            for line in output.getvalue().replace("\r\n", "\n").splitlines()
        ).strip()
        + "\n"
    )
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

    for forbidden in ("DROP", "TRUNCATE", "DELETE", "COPY"):
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

    created_table_items = re.findall(
        r"CREATE TABLE ntubtob\.([a-z_]+)", sql, flags=re.IGNORECASE
    )
    created_tables = set(created_table_items)
    expected_created_tables = EXPECTED_TABLES | {"alembic_version"}
    if (
        len(created_table_items) != len(expected_created_tables)
        or created_tables != expected_created_tables
    ):
        _fail(errors, f"unexpected created tables: {sorted(created_tables)}")
    if created_tables & LEGACY_TABLES:
        _fail(errors, "artifact attempts to create a catalog-owned legacy table")

    marker_create = re.findall(
        r"CREATE TABLE ntubtob\.alembic_version\s*\(\s*"
        r"version_num VARCHAR\(32\) NOT NULL,\s*"
        r"CONSTRAINT alembic_version_pkc PRIMARY KEY \(version_num\)\s*\);",
        sql,
        flags=re.IGNORECASE,
    )
    if len(marker_create) != 1:
        _fail(
            errors,
            "canonical Alembic version table creation is missing or duplicated",
        )

    baseline_inserts = re.findall(
        r"^INSERT INTO ntubtob\.alembic_version \(version_num\) VALUES "
        r"\('([^']+)'\) RETURNING ntubtob\.alembic_version\.version_num;$",
        sql,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if baseline_inserts != ["0001_legacy_baseline"]:
        _fail(errors, "exactly one canonical 0001 baseline insert is required")

    all_inserts = re.findall(
        r"^\s*INSERT\s+INTO\s+([^\s(]+)",
        sql,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if [target.lower() for target in all_inserts] != ["ntubtob.alembic_version"]:
        _fail(errors, "baseline bookkeeping is the only allowed INSERT")

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
            "add constraint fk_members_person foreign key (person_id) "
            "references ntubtob.people(id) on delete restrict",
        ),
        (
            "activities",
            "alter column game_id type bigint using game_id::bigint",
        ),
    } | {(table, "enable row level security") for table in EXPECTED_TABLES}
    normalized_alters = {
        (table.lower(), " ".join(body.lower().split())) for table, body in alters
    }
    if len(alters) != len(allowed_alters) or normalized_alters != allowed_alters:
        _fail(errors, f"unexpected ALTER TABLE statements: {sorted(normalized_alters)}")

    rls_tables = re.findall(
        r"^\s*ALTER TABLE ntubtob\.([a-z_]+) ENABLE ROW LEVEL SECURITY;$",
        sql,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if len(rls_tables) != len(EXPECTED_TABLES) or set(rls_tables) != EXPECTED_TABLES:
        _fail(errors, "exactly the 13 expected portal tables must enable RLS")
    for forbidden_rls in (
        r"\bCREATE\s+POLICY\b",
        r"\bALTER\s+POLICY\b",
        r"\bFORCE\s+ROW\s+LEVEL\s+SECURITY\b",
        r"^\s*(?:GRANT|REVOKE)\b",
    ):
        if re.search(forbidden_rls, sql, flags=re.IGNORECASE | re.MULTILINE):
            _fail(errors, f"forbidden RLS or privilege statement: {forbidden_rls}")

    index_items = re.findall(
        r"^\s*CREATE INDEX ([a-z_]+)\s+ON ntubtob\.([a-z_]+)",
        sql,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    indexes = {(name.lower(), table.lower()) for name, table in index_items}
    if len(index_items) != len(EXPECTED_INDEXES) or indexes != EXPECTED_INDEXES:
        _fail(errors, f"unexpected CREATE INDEX statements: {sorted(indexes)}")

    functions = re.findall(
        r"^\s*CREATE FUNCTION ntubtob\.([a-z_]+)\(\)",
        sql,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if functions != ["reject_audit_mutation"]:
        _fail(errors, f"unexpected CREATE FUNCTION statements: {functions}")

    trigger_items = re.findall(
        r"^\s*CREATE TRIGGER ([a-z_]+).*? ON ntubtob\.([a-z_]+)",
        sql,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    triggers = {(name.lower(), table.lower()) for name, table in trigger_items}
    if len(trigger_items) != len(EXPECTED_TRIGGERS) or triggers != EXPECTED_TRIGGERS:
        _fail(errors, f"unexpected CREATE TRIGGER statements: {sorted(triggers)}")

    create_kinds = re.findall(
        r"^\s*CREATE\s+(?:UNIQUE\s+)?([A-Z]+)",
        sql,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    allowed_create_kinds = {"TABLE", "INDEX", "FUNCTION", "TRIGGER"}
    if any(kind.upper() not in allowed_create_kinds for kind in create_kinds):
        _fail(errors, f"unexpected CREATE statement kind: {create_kinds}")

    updates = re.findall(
        r"^UPDATE ntubtob\.alembic_version SET version_num='([^']+)' "
        r"WHERE ntubtob\.alembic_version\.version_num = '([^']+)';$",
        sql,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    expected_updates = [
        ("0002_portal_data_foundation", "0001_legacy_baseline"),
        ("0003_legacy_bigint_activity_game", "0002_portal_data_foundation"),
    ]
    if updates != expected_updates:
        _fail(errors, "only the two exact Alembic version updates are allowed")

    if expected_checksum is not None and checksum_for(sql) != expected_checksum.strip():
        _fail(errors, "artifact checksum does not match its reviewed sidecar")
    if sql != render_sql():
        _fail(errors, "SQL differs from the deterministic Alembic artifact")
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
