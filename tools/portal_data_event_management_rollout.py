"""Fail-closed TASK-164 production migration operator.

The operator accepts one caller-owned private PostgreSQL URL in memory.  It
never discovers credentials, logs connection details, or retries execution.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Callable

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "tools" / "portal_data_event_management_rollout.py"
CHECKSUM = ARTIFACT.with_suffix(".py.sha256")
MIGRATION = ROOT / "migrations" / "versions" / "0009_event_management_writes.py"
SOURCE_REVISION = "0008_mobile_notification_delivery"
TARGET_REVISION = "0009_event_management_writes"
EXECUTION_ACKNOWLEDGEMENT = "EXECUTE TASK-164 0008 TO 0009"
ADVISORY_LOCK_KEY = 1640009
APPEND_ONLY_BODY_SHA256 = (
    "d24dc1c8bd05ac503ab853c62eab84a4968b79dabd2c535e678ec002af5bdd68"
)
OLD_ACTIONS = ("published", "invitee_included", "invitee_excluded")
NEW_ACTIONS = (
    "published",
    "edited",
    "cancelled",
    "invitee_included",
    "invitee_excluded",
)
EVENT_TABLES = (
    "activities",
    "activity_attendance_replies",
    "event_attendance_replies",
    "event_audit",
    "event_eligibility_rules",
    "event_invitee_overrides",
    "event_invitees",
    "event_managers",
    "events",
)


class RolloutError(RuntimeError):
    """Raised when the production migration boundary cannot be proven exact."""


def _canonical_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_artifact() -> None:
    digest, separator, name = (
        CHECKSUM.read_text(encoding="ascii").strip().partition("  ")
    )
    if not separator or name != ARTIFACT.name or digest != _canonical_digest(ARTIFACT):
        raise RolloutError("operator checksum boundary is invalid")
    scripts = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    if scripts.get_heads() != [TARGET_REVISION]:
        raise RolloutError("repository migration graph is divergent")


def _current_revision(connection: Connection) -> str:
    rows = (
        connection.execute(text("SELECT version_num FROM ntubtob.alembic_version"))
        .scalars()
        .all()
    )
    if len(rows) != 1 or not isinstance(rows[0], str):
        raise RolloutError("Alembic revision is ambiguous")
    return rows[0]


def _constraint_actions(connection: Connection) -> tuple[str, ...]:
    row = connection.execute(
        text(
            "SELECT c.contype,c.convalidated,pg_get_constraintdef(c.oid,true) "
            "FROM pg_constraint c "
            "JOIN pg_class t ON t.oid=c.conrelid "
            "JOIN pg_namespace n ON n.oid=t.relnamespace "
            "WHERE n.nspname='ntubtob' AND t.relname='event_audit' "
            "AND c.conname='ck_event_audit_action'"
        )
    ).all()
    if len(row) != 1:
        raise RolloutError("event audit constraint is ambiguous")
    constraint_type, validated, definition = row[0]
    if (
        constraint_type != "c"
        or validated is not True
        or not isinstance(definition, str)
        or not definition.startswith("CHECK (")
        or "action" not in definition
        or " NOT VALID" in definition.upper()
    ):
        raise RolloutError("event audit constraint drifted")
    actions = tuple(re.findall(r"'([^']+)'", definition))
    expression = re.sub(r"'[^']+'", "", definition)
    words = tuple(word.lower() for word in re.findall(r"[A-Za-z_]+", expression))
    allowed_words = {"check", "action", "any", "array", "text", "character", "varying"}
    if (
        any(word not in allowed_words for word in words)
        or words.count("check") != 1
        or words.count("action") != 1
        or words.count("any") != 1
        or words.count("array") != 1
        or definition.count("=") != 1
        or any(token in expression for token in ("<", ">", "!", ";"))
    ):
        raise RolloutError("event audit constraint expression drifted")
    return actions


def _catalog_safe(connection: Connection, expected_actions: tuple[str, ...]) -> None:
    if _constraint_actions(connection) != expected_actions:
        raise RolloutError("event audit action contract drifted")
    rls_rows = connection.execute(
        text(
            "SELECT relname,relrowsecurity,relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='ntubtob' AND relname=ANY(:tables) "
            "ORDER BY relname"
        ),
        {"tables": list(EVENT_TABLES)},
    ).all()
    if len(rls_rows) != len(EVENT_TABLES) or any(
        row.relname != table
        or row.relrowsecurity is not True
        or row.relforcerowsecurity is not False
        for row, table in zip(rls_rows, EVENT_TABLES)
    ):
        raise RolloutError("event RLS contract drifted")
    policy_count = int(
        connection.scalar(
            text(
                "SELECT count(*) FROM pg_policy p "
                "JOIN pg_class c ON c.oid=p.polrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='ntubtob' AND c.relname=ANY(:tables)"
            ),
            {"tables": list(EVENT_TABLES)},
        )
        or 0
    )
    if policy_count != 0:
        raise RolloutError("event policy boundary drifted")
    _validate_append_only(connection)


def _canonical_sql(value: str) -> str:
    return " ".join(value.split())


def _validate_append_only(connection: Connection) -> None:
    rows = connection.execute(
        text(
            "SELECT t.tgenabled,t.tgtype,t.tgnargs,t.tgattr::text,t.tgqual,"
            "t.tgconstraint,t.tgoldtable,t.tgnewtable,t.tgdeferrable,"
            "t.tginitdeferred,fn_ns.nspname,p.pronargs,"
            "p.prorettype='trigger'::regtype,l.lanname,p.prosrc "
            "FROM pg_trigger t "
            "JOIN pg_class c ON c.oid=t.tgrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "JOIN pg_proc p ON p.oid=t.tgfoid "
            "JOIN pg_namespace fn_ns ON fn_ns.oid=p.pronamespace "
            "JOIN pg_language l ON l.oid=p.prolang "
            "WHERE n.nspname='ntubtob' AND c.relname='event_audit' "
            "AND t.tgname='event_audit_append_only' AND NOT t.tgisinternal "
            "AND p.proname='reject_audit_mutation'"
        )
    ).all()
    if len(rows) != 1:
        raise RolloutError("event audit append-only boundary is ambiguous")
    (
        enabled,
        trigger_type,
        trigger_args,
        update_columns,
        when_clause,
        constraint_oid,
        old_transition_table,
        new_transition_table,
        deferrable,
        initially_deferred,
        function_schema,
        function_args,
        returns_trigger,
        language,
        body,
    ) = rows[0]
    body_digest = (
        hashlib.sha256(_canonical_sql(body).encode("utf-8")).hexdigest()
        if isinstance(body, str)
        else ""
    )
    if enabled != "O" or trigger_type != 27 or trigger_args != 0:
        raise RolloutError("event audit append-only mismatch: trigger_core")
    if update_columns != "":
        raise RolloutError("event audit append-only mismatch: trigger_columns")
    if when_clause is not None:
        raise RolloutError("event audit append-only mismatch: trigger_when")
    if constraint_oid != 0:
        raise RolloutError("event audit append-only mismatch: trigger_constraint")
    if old_transition_table is not None or new_transition_table is not None:
        raise RolloutError("event audit append-only mismatch: trigger_transition")
    if deferrable is not False or initially_deferred is not False:
        raise RolloutError("event audit append-only mismatch: trigger_deferrability")
    if (
        function_schema != "ntubtob"
        or function_args != 0
        or returns_trigger is not True
        or language != "plpgsql"
    ):
        raise RolloutError("event audit append-only mismatch: function_identity")
    if body_digest != APPEND_ONLY_BODY_SHA256:
        raise RolloutError("event audit append-only mismatch: function_body")


def _logging_safe(connection: Connection) -> bool:
    row = connection.execute(
        text(
            "SELECT "
            "coalesce(current_setting('log_statement',true),'all') IN ('none','ddl'),"
            "coalesce(current_setting('log_min_duration_statement',true),'0')::integer=-1,"
            "coalesce(current_setting('log_min_duration_sample',true),'0')::integer=-1,"
            "coalesce(current_setting('log_duration',true),'on')='off',"
            "coalesce(current_setting('log_transaction_sample_rate',true),'1')::numeric=0,"
            "coalesce(current_setting('pgaudit.log',true),'none') IN ('none',''),"
            "coalesce(current_setting('log_parameter_max_length_on_error',true),'-1')::integer=0"
        )
    ).one()
    return all(value is True for value in row)


def _application_dml_count(connection: Connection) -> int:
    return int(
        connection.scalar(
            text(
                "SELECT coalesce(sum(n_tup_ins+n_tup_upd+n_tup_del),0) "
                "FROM pg_stat_xact_user_tables "
                "WHERE schemaname='ntubtob' AND relname<>'alembic_version'"
            )
        )
        or 0
    )


def _upgrade(connection: Connection) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    command.upgrade(config, TARGET_REVISION)


def _run_locked(
    connection: Connection,
    *,
    execute: bool,
    fail_after_migration: bool = False,
    migration_runner: Callable[[Connection], None] = _upgrade,
) -> dict[str, object]:
    connection.execute(text("SET LOCAL statement_timeout = '30s'"))
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL idle_in_transaction_session_timeout = '45s'"))
    connection.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADVISORY_LOCK_KEY}
    )
    revision = _current_revision(connection)
    if revision != SOURCE_REVISION:
        if revision == TARGET_REVISION:
            raise RolloutError("event migration is already forward; do not retry")
        raise RolloutError("event migration revision drifted")
    if not _logging_safe(connection):
        raise RolloutError("database logging boundary is unsafe")
    _catalog_safe(connection, OLD_ACTIONS)
    if _application_dml_count(connection) != 0:
        raise RolloutError("transaction contains prior application DML")
    if not execute:
        return {
            "mode": "dry-run",
            "status": "ready",
            "source_revision": SOURCE_REVISION,
            "target_revision": TARGET_REVISION,
            "application_dml_count": 0,
        }

    migration_runner(connection)
    if fail_after_migration:
        raise RolloutError("injected migration failure")
    if _current_revision(connection) != TARGET_REVISION:
        raise RolloutError("event migration postcheck revision failed")
    _catalog_safe(connection, NEW_ACTIONS)
    dml_count = _application_dml_count(connection)
    if dml_count != 0:
        raise RolloutError("event migration performed application DML")
    return {
        "mode": "execute",
        "status": "applied",
        "source_revision": SOURCE_REVISION,
        "target_revision": TARGET_REVISION,
        "application_dml_count": 0,
    }


def run(
    mode: str,
    database_url: str,
    acknowledgement: str | None = None,
    *,
    engine_factory: Callable[..., Engine] = create_engine,
) -> dict[str, object]:
    verify_artifact()
    if mode not in {"dry-run", "execute"}:
        raise RolloutError("rollout mode is invalid")
    execute = mode == "execute"
    if execute and acknowledgement != EXECUTION_ACKNOWLEDGEMENT:
        raise RolloutError("event migration execution is not acknowledged")
    if not execute and acknowledgement is not None:
        raise RolloutError("dry-run rejects execution acknowledgement")
    engine = engine_factory(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            if not execute:
                connection.execute(text("SET TRANSACTION READ ONLY"))
            result = _run_locked(connection, execute=execute)
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
        return result
    finally:
        engine.dispose()


def main() -> None:
    raise SystemExit("TASK-164 operator requires its reviewed launcher")


if __name__ == "__main__":
    main()
