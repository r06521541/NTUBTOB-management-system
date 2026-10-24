"""Default-unused exact structured-store deletion in one local transaction.

This item is not full erasure: identities, provider credentials, shared content,
audits and the Person survive. No external I/O, new authorization or job completion
is provided. The trusted planner must capture this same inventory under canonical
locks and bind it to an immutable online_erasure item before calling execute.
"""

import hashlib
import hmac
import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..mobile_api import utc_now
from .erasure_legacy_execution import LegacyExecutionResult
from .erasure_provider_execution import _Rejected, _target, _time, _uuid
from .erasure_retention import retention_failure_reason
from .runtime import acquire_admin_event_locks

# Children are explicit; deleting a session must not silently rely on CASCADE.
DELETE_ORDER = (
    "mobile_refresh_attempts",
    "mobile_auth_exchanges",
    "mobile_idempotency_records",
    "mobile_device_registrations",
    "mobile_refresh_tokens",
    "mobile_sessions",
    "mobile_notification_deliveries",
    "mobile_notification_recipients",
    "event_attendance_replies",
    "activity_attendance_replies",
)
INVENTORY_TABLES = (
    "people",
    "auth_identities",
    *DELETE_ORDER,
    "mobile_notifications",
    "mobile_notification_publish_audits",
    "event_notification_publish_audits",
)


@dataclass(frozen=True, repr=False)
class StructuredInventory:
    person_id: int
    identities: tuple
    rows: tuple
    delivery_proofs: tuple


def structured_item_binding(job_id, generation, inventory):
    """Internal inventory digest, not a receipt, authorization or public output."""
    if type(inventory) is not StructuredInventory:
        raise _Rejected("invalid_inventory")
    return hashlib.sha256(
        json.dumps(
            [
                "structured_erasure_v1",
                _uuid(job_id),
                _uuid(generation),
                inventory.person_id,
                inventory.identities,
                inventory.rows,
                inventory.delivery_proofs,
            ],
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _rows(connection, sql, **parameters):
    return tuple(tuple(row) for row in connection.execute(text(sql), parameters))


def _locked_inventory(connection, person_id):
    """Internal planner/executor helper; canonical locks must already be held.

    Relation locks drain non-cooperating DML and protect ownership joins/phantoms.
    Do not project credentials, token hashes, response JSON, names or message text.
    The caller must use a bounded, clean READ COMMITTED transaction.
    """
    connection.execute(
        text(
            "LOCK TABLE "
            + ",".join("ntubtob." + name for name in INVENTORY_TABLES)
            + " IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    cascades = _rows(
        connection,
        "SELECT ns.nspname,src.relname,dst.relname,c.confdeltype, "
        "ARRAY(SELECT a.attname::text FROM unnest(c.conkey) WITH ORDINALITY k(attnum,ord) "
        "JOIN pg_catalog.pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.attnum ORDER BY k.ord), "
        "ARRAY(SELECT a.attname::text FROM unnest(c.confkey) WITH ORDINALITY k(attnum,ord) "
        "JOIN pg_catalog.pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.attnum ORDER BY k.ord) "
        "FROM pg_catalog.pg_constraint c "
        "JOIN pg_catalog.pg_class src ON src.oid=c.conrelid "
        "JOIN pg_catalog.pg_namespace ns ON ns.oid=src.relnamespace "
        "JOIN pg_catalog.pg_class dst ON dst.oid=c.confrelid "
        "JOIN pg_catalog.pg_namespace nd ON nd.oid=dst.relnamespace "
        "WHERE c.contype='f' AND c.confdeltype IN ('c','n','d') AND nd.nspname='ntubtob' "
        "AND dst.relname=ANY(:tables)",
        tables=list(DELETE_ORDER),
    )
    allowed = {
        ("ntubtob", table, "mobile_sessions", "c", ("session_id",), ("id",))
        for table in (
            "mobile_refresh_tokens",
            "mobile_refresh_attempts",
            "mobile_idempotency_records",
        )
    }
    edges = tuple(edge[:4] + (tuple(edge[4]), tuple(edge[5])) for edge in cascades)
    if len(edges) != len(set(edges)) or any(edge not in allowed for edge in edges):
        raise _Rejected("unreviewed_cascade")
    identities = _rows(
        connection,
        "SELECT id,account_generation::text FROM ntubtob.auth_identities "
        "WHERE person_id=:person ORDER BY id",
        person=person_id,
    )
    identity_ids = [row[0] for row in identities]
    sessions = _rows(
        connection,
        "SELECT id,person_id,auth_identity_id FROM ntubtob.mobile_sessions "
        "WHERE person_id=:person OR auth_identity_id=ANY(:identities) ORDER BY id",
        person=person_id,
        identities=identity_ids,
    )
    if any(row[1] != person_id or row[2] not in identity_ids for row in sessions):
        raise _Rejected("ownership_conflict")
    session_ids = [row[0] for row in sessions]
    rows = {"mobile_sessions": sessions}
    for table in ("mobile_idempotency_records", "mobile_device_registrations"):
        rows[table] = _rows(
            connection,
            f"SELECT id,person_id,session_id FROM ntubtob.{table} "
            "WHERE person_id=:person OR session_id=ANY(:sessions) ORDER BY id",
            person=person_id,
            sessions=session_ids,
        )
        if any(row[1] != person_id or row[2] not in session_ids for row in rows[table]):
            raise _Rejected("ownership_conflict")
    for table in ("mobile_refresh_attempts", "mobile_auth_exchanges"):
        rows[table] = _rows(
            connection,
            f"SELECT id,session_id FROM ntubtob.{table} "
            "WHERE session_id=ANY(:sessions) ORDER BY id",
            sessions=session_ids,
        )
    tokens = _rows(
        connection,
        "SELECT id,session_id,successor_token_id FROM ntubtob.mobile_refresh_tokens "
        "WHERE session_id=ANY(:sessions) ORDER BY id",
        sessions=session_ids,
    )
    token_sessions = {row[0]: row[1] for row in tokens}
    incoming = _rows(
        connection,
        "SELECT id,session_id,successor_token_id FROM ntubtob.mobile_refresh_tokens "
        "WHERE successor_token_id=ANY(:tokens) ORDER BY id",
        tokens=list(token_sessions),
    )
    if any(
        row[0] not in token_sessions
        or (row[2] is not None and token_sessions.get(row[2]) != row[1])
        for row in tokens + incoming
    ):
        raise _Rejected("ownership_conflict")
    rows["mobile_refresh_tokens"] = tokens
    for table, parent in (
        ("mobile_notification_recipients", "notification_id"),
        ("event_attendance_replies", "event_id"),
        ("activity_attendance_replies", "activity_id"),
    ):
        rows[table] = _rows(
            connection,
            f"SELECT id,person_id,{parent} FROM ntubtob.{table} "
            "WHERE person_id=:person ORDER BY id",
            person=person_id,
        )
    # Deliveries are aggregate rows. Never infer ownership from the last remaining
    # recipient alone; original individual audience evidence is also required.
    proofs = _rows(
        connection,
        "SELECT a.id,a.notification_id,a.audience_reference_id,a.recipient_count "
        "FROM ntubtob.mobile_notification_publish_audits a "
        "WHERE a.audience_type='individual' AND a.audience_reference_id=:person "
        "AND a.recipient_count=1 "
        "AND EXISTS (SELECT 1 FROM ntubtob.mobile_notification_recipients r "
        "WHERE r.notification_id=a.notification_id AND r.person_id=:person) "
        "AND NOT EXISTS (SELECT 1 FROM ntubtob.mobile_notification_recipients r "
        "WHERE r.notification_id=a.notification_id AND r.person_id<>:person) "
        "AND NOT EXISTS (SELECT 1 FROM ntubtob.event_notification_publish_audits e "
        "WHERE e.notification_id=a.notification_id) ORDER BY a.id",
        person=person_id,
    )
    rows["mobile_notification_deliveries"] = _rows(
        connection,
        "SELECT id,notification_id FROM ntubtob.mobile_notification_deliveries "
        "WHERE notification_id=ANY(:notifications) ORDER BY id",
        notifications=[row[1] for row in proofs],
    )
    return StructuredInventory(
        person_id,
        identities,
        tuple((table, rows[table]) for table in DELETE_ORDER),
        proofs,
    )


def _connection(session):
    if not session.in_transaction() or session.new or session.dirty or session.deleted:
        raise _Rejected("clean_transaction_required")
    connection = session.connection()
    if (
        connection.get_isolation_level() != "READ COMMITTED"
        or getattr(connection.connection.dbapi_connection, "autocommit", None)
        is not False
    ):
        raise _Rejected("read_committed_required")
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL statement_timeout = '5s'"))
    acquire_admin_event_locks(connection)
    if tuple(
        connection.scalars(text("SELECT version_num FROM ntubtob.alembic_version"))
    ) not in (
        ("0018_erasure_privacy_mutation",),
        ("0019_erasure_admin_recovery",),
        ("0020_erasure_intake",),
        ("0021_erasure_continuity",),
        ("0022_erasure_retention",),
        ("0023_erasure_minimal_retention",),
    ):
        raise _Rejected("schema_not_ready")
    for table in (
        "account_erasure_jobs",
        "account_erasure_items",
        "account_erasure_item_events",
        *INVENTORY_TABLES,
    ):
        if (
            connection.scalar(
                text(
                    f"SELECT pg_catalog.row_security_active('ntubtob.{table}'::regclass)"
                )
            )
            is not False
        ):
            raise _Rejected("unfiltered_tables_required")
    return connection


def _locked_context(connection, job_id, item_id):
    job = (
        connection.execute(
            text("SELECT * FROM ntubtob.account_erasure_jobs WHERE id=:id FOR UPDATE"),
            {"id": job_id},
        )
        .mappings()
        .first()
    )
    if (
        job is None
        or job["status"] not in {"verified", "processing", "needs_attention"}
        or job["target_kind"] != "person"
    ):
        raise _Rejected("verified_person_job_required")
    _target(connection, job)
    item = (
        connection.execute(
            text(
                "SELECT * FROM ntubtob.account_erasure_items "
                "WHERE id=:id AND job_id=:job FOR UPDATE"
            ),
            {"id": item_id, "job": job_id},
        )
        .mappings()
        .first()
    )
    if (
        item is None
        or item["stage"] != "online_erasure"
        or item["expected_generation"] != job["expected_generation"]
    ):
        raise _Rejected("item_scope_changed")
    if connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM ntubtob.account_erasure_item_events WHERE item_id=:id)"
        ),
        {"id": item_id},
    ):
        raise _Rejected("item_already_started")
    return job, item


def _delete_inventory(connection, inventory):
    for table, rows in inventory.rows:
        identifiers = [row[0] for row in rows]
        if not identifiers:
            continue
        result = connection.execute(
            text(f"DELETE FROM ntubtob.{table} WHERE id=ANY(:ids)"),
            {"ids": identifiers},
        )
        if (
            result.rowcount != len(identifiers)
            or connection.scalar(
                text(f"SELECT count(*) FROM ntubtob.{table} WHERE id=ANY(:ids)"),
                {"ids": identifiers},
            )
            != 0
        ):
            raise _Rejected("disposition_count_changed")
    remaining = _locked_inventory(connection, inventory.person_id)
    if any(rows for _, rows in remaining.rows):
        raise _Rejected("disposition_incomplete")


class StructuredErasureExecutor:
    def __init__(self, engine, *, clock=utc_now, scope_validator=None):
        if (
            not isinstance(engine, Engine)
            or not callable(clock)
            or (scope_validator is not None and not callable(scope_validator))
        ):
            raise ValueError("invalid_executor_configuration")
        self.engine, self.clock = engine, clock
        # Trusted local composition only: read on this locked transaction, raise
        # on mismatch, return None. Never perform I/O, commit, or accept user code.
        self.scope_validator = scope_validator

    def execute(self, *, job_id, item_id):
        stage = "input"
        try:
            _uuid(job_id)
            _uuid(item_id)
            stage = "preparation"
            with Session(self.engine) as session, session.begin():
                connection = _connection(session)
                job, item = _locked_context(connection, job_id, item_id)
                inventory = _locked_inventory(connection, job["person_id"])
                if not any(rows for _, rows in inventory.rows):
                    raise _Rejected("empty_scope")
                if not hmac.compare_digest(
                    structured_item_binding(
                        job_id, str(job["expected_generation"]), inventory
                    ),
                    item["binding_hash"],
                ):
                    raise _Rejected("inventory_changed")
                if self.scope_validator is not None:
                    stage = "sealed_scope"
                    if self.scope_validator(connection, job, item) is not None:
                        raise _Rejected("scope_validator_rejected")
                    stage = "preparation"
                now = _time(self.clock())
                if now < max(_time(job["updated_at"]), _time(item["created_at"])):
                    raise _Rejected("clock_regressed")
                connection.execute(
                    text(
                        "UPDATE ntubtob.account_erasure_jobs SET status='processing',"
                        "irreversible_started_at=COALESCE(irreversible_started_at,:now),"
                        "updated_at=:now WHERE id=:id"
                    ),
                    {"id": job_id, "now": now},
                )
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.account_erasure_item_events "
                        "(item_id,event_sequence,event_kind,result_code,occurred_at) "
                        "VALUES (:id,1,'started','in_progress',:now)"
                    ),
                    {"id": item_id, "now": now},
                )
                stage = "disposition"
                _delete_inventory(connection, inventory)
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.account_erasure_item_events "
                        "(item_id,event_sequence,event_kind,result_code,occurred_at) "
                        "VALUES (:id,2,'confirmed','succeeded',:now)"
                    ),
                    {"id": item_id, "now": now},
                )
                stage = "commit"
        except _Rejected as error:
            return LegacyExecutionResult("not_applied", stage, str(error))
        except Exception as error:
            if stage != "commit" and (reason := retention_failure_reason(error)):
                return LegacyExecutionResult("not_applied", stage, reason)
            return LegacyExecutionResult(
                "outcome_unknown" if stage == "commit" else "not_applied",
                stage,
                "commit_unconfirmed" if stage == "commit" else "transaction_failed",
            )
        return LegacyExecutionResult(
            "confirmed", "commit", "item_completed", "next_item"
        )
