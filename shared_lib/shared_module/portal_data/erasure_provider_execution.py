"""Default-unused, one-shot per-item provider dispatch after durable fencing.

Trusted prepare_effect is local/read-only and resolves the exact reviewed item,
current provider credential version and scope. It returns an in-memory callable,
not serialized private data. No external I/O may occur during preparation.
This coordinator neither authorizes operators nor completes account erasure.
No retries: already-started and any uncertain commit require read-only review.
"""

import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..mobile_api import utc_now
from .runtime import acquire_admin_event_locks


@dataclass(frozen=True, repr=False)
class PreparedProviderEffect:
    binding_hash: str
    scope_hash: str
    expected_generation: str
    invoke: Callable[[], str]


@dataclass(frozen=True)
class ProviderExecutionResult:
    classification: str
    stage: str
    reason: str
    effect_result: str | None = None
    next_action: str = "read_only_review"


class _Rejected(ValueError):
    pass


def _uuid(value):
    try:
        if type(value) is str and str(UUID(value)) == value:
            return value
    except ValueError:
        pass
    raise _Rejected("invalid_identifier")


def _hash(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _time(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise _Rejected("invalid_clock")
    return value.astimezone(timezone.utc)


def _connection(session):
    if not session.in_transaction() or session.new or session.dirty or session.deleted:
        raise _Rejected("clean_transaction_required")
    connection = session.connection()
    if (
        getattr(connection.connection.dbapi_connection, "autocommit", None) is not False
        or connection.get_isolation_level() != "READ COMMITTED"
    ):
        raise _Rejected("read_committed_required")
    acquire_admin_event_locks(connection)
    if tuple(
        connection.scalars(
            text("SELECT version_num FROM ntubtob.alembic_version")
        ).all()
    ) not in (
        ("0017_erasure_work_items",),
        ("0018_erasure_privacy_mutation",),
        ("0019_erasure_admin_recovery",),
        ("0020_erasure_intake",),
        ("0021_erasure_continuity",),
    ):
        raise _Rejected("schema_not_ready")
    for table in (
        "account_erasure_jobs",
        "account_erasure_items",
        "account_erasure_item_events",
        "people",
        "auth_identities",
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


def _locked(connection, job_id, item_id):
    job = (
        connection.execute(
            text("SELECT * FROM ntubtob.account_erasure_jobs WHERE id=:id FOR UPDATE"),
            {"id": job_id},
        )
        .mappings()
        .first()
    )
    if job is None or job["status"] not in {
        "verified",
        "processing",
        "needs_attention",
    }:
        raise _Rejected("verified_job_required")
    item = (
        connection.execute(
            text(
                "SELECT * FROM ntubtob.account_erasure_items WHERE id=:id AND job_id=:job FOR UPDATE"
            ),
            {"id": item_id, "job": job_id},
        )
        .mappings()
        .first()
    )
    if (
        item is None
        or item["stage"] != "provider_revocation"
        or str(item["expected_generation"]) != str(job["expected_generation"])
    ):
        raise _Rejected("item_scope_changed")
    return job, item


def _target(connection, job):
    if job["target_kind"] == "person" and job["auth_identity_id"] is None:
        table, identifier = "people", job["person_id"]
    elif job["target_kind"] == "pending_identity" and job["person_id"] is None:
        table, identifier = "auth_identities", job["auth_identity_id"]
    else:
        raise _Rejected("target_scope_changed")
    if type(identifier) is not int or identifier <= 0:
        raise _Rejected("target_scope_changed")
    columns = "account_generation" + (
        ",person_id,status" if table == "auth_identities" else ""
    )
    target = (
        connection.execute(
            text(f"SELECT {columns} FROM ntubtob.{table} WHERE id=:id FOR UPDATE"),
            {"id": identifier},
        )
        .mappings()
        .first()
    )
    if target is None or str(target["account_generation"]) != str(
        job["expected_generation"]
    ):
        raise _Rejected("target_scope_changed")
    if table == "auth_identities" and (
        target["person_id"] is not None
        or target["status"] not in {"pending", "blocked", "disabled"}
    ):
        raise _Rejected("target_scope_changed")


class ProviderErasureExecutor:
    """No dispatch until Session.begin exits successfully (commit acknowledged).

    The injected session factory must create independent real transactions, never
    savepoints in an outer transaction. Normal construction does this via engine.
    prepare_effect must not issue external calls, mutate rows or commit the Session.
    Explicit reconciliation is separate; repeating execute never dispatches again.
    """

    RESULTS = frozenset(
        {"succeeded", "credential_missing", "manual_action_needed", "not_applicable"}
    )

    def __init__(self, engine, prepare_effect, *, clock=utc_now):
        if (
            not isinstance(engine, Engine)
            or not callable(prepare_effect)
            or not callable(clock)
        ):
            raise ValueError("invalid_executor_configuration")
        self.engine, self.prepare_effect, self.clock = engine, prepare_effect, clock

    def execute(self, *, job_id, item_id):
        stage = "input"
        try:
            _uuid(job_id)
            _uuid(item_id)
            stage = "preparation"
            with Session(self.engine) as session, session.begin():
                connection = _connection(session)
                job, item = _locked(connection, job_id, item_id)
                _target(connection, job)
                if connection.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM ntubtob.account_erasure_item_events WHERE item_id=:id)"
                    ),
                    {"id": item_id},
                ):
                    raise _Rejected("item_already_started")
                prepared = self.prepare_effect(connection, job, item)
                if (
                    type(prepared) is not PreparedProviderEffect
                    or not callable(prepared.invoke)
                    or not _hash(prepared.binding_hash)
                    or not _hash(prepared.scope_hash)
                    or not hmac.compare_digest(
                        prepared.binding_hash, item["binding_hash"]
                    )
                    or not hmac.compare_digest(prepared.scope_hash, job["scope_hash"])
                    or prepared.expected_generation != str(job["expected_generation"])
                ):
                    raise _Rejected("prepared_scope_changed")
                now = _time(self.clock())
                if now < max(_time(job["updated_at"]), _time(item["created_at"])):
                    raise _Rejected("clock_regressed")
                connection.execute(
                    text(
                        "UPDATE ntubtob.account_erasure_jobs SET status='processing', "
                        "irreversible_started_at=COALESCE(irreversible_started_at,:now),updated_at=:now WHERE id=:id"
                    ),
                    {"now": now, "id": job_id},
                )
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.account_erasure_item_events (item_id,event_sequence,event_kind,result_code,occurred_at) "
                        "VALUES (:id,1,'started','in_progress',:now)"
                    ),
                    {"id": item_id, "now": now},
                )
                stage = "fence_commit"
        except _Rejected as error:
            return ProviderExecutionResult("not_dispatched", stage, str(error))
        except Exception:
            return ProviderExecutionResult("not_dispatched", stage, "fence_unconfirmed")

        # No Session/transaction is live while contacting the provider.
        effect_result = None
        try:
            result = prepared.invoke()
            if type(result) is str and result in self.RESULTS:
                effect_result = result
        except Exception:
            pass  # No raw provider exception or token-bearing response is retained.
        try:
            with Session(self.engine) as session, session.begin():
                connection = _connection(session)
                job, item = _locked(connection, job_id, item_id)
                if job["irreversible_started_at"] is None:
                    raise _Rejected("dispatch_fence_missing")
                now = _time(self.clock())
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.account_erasure_item_events (item_id,event_sequence,event_kind,result_code,occurred_at) "
                        "VALUES (:id,2,:kind,:result,:now)"
                    ),
                    {
                        "id": item_id,
                        "kind": "confirmed" if effect_result else "unknown",
                        "result": effect_result or "response_unknown",
                        "now": now,
                    },
                )
                if effect_result is None:
                    connection.execute(
                        text(
                            "UPDATE ntubtob.account_erasure_jobs SET status='needs_attention',updated_at=:now WHERE id=:id"
                        ),
                        {"id": job_id, "now": now},
                    )
        except Exception:
            return ProviderExecutionResult(
                "outcome_unknown",
                "result_commit",
                "evidence_unconfirmed",
                effect_result,
            )
        if effect_result is None:
            return ProviderExecutionResult(
                "outcome_unknown", "provider", "response_unknown"
            )
        return ProviderExecutionResult(
            "confirmed",
            "result_commit",
            "evidence_recorded",
            effect_result,
            "next_item",
        )
