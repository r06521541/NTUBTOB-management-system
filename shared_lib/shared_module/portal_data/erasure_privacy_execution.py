"""Internal exact-item disposition; not a public redaction or job completion API.

Only trusted reviewed inventory supplies the replacement and immutable binding.
The SQL capability rechecks the exact old row, ownership, generation and fields.
All local effects and item evidence commit together. No raw replacement, database
exception, original row or digest is included in returned diagnostic evidence.
"""

import json

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..mobile_api import utc_now
from .erasure_legacy_execution import LegacyExecutionResult
from .erasure_provider_execution import _Rejected, _target, _time, _uuid
from .erasure_retention import retention_failure_reason
from .runtime import acquire_admin_event_locks


class PrivacyDispositionExecutor:
    def __init__(self, engine, *, clock=utc_now, scope_validator=None):
        if (
            not isinstance(engine, Engine)
            or not callable(clock)
            or (scope_validator is not None and not callable(scope_validator))
        ):
            raise ValueError("invalid_executor_configuration")
        self.engine, self.clock = engine, clock
        # Trusted local read-only composition, not user code. No I/O or commit.
        self.scope_validator = scope_validator

    def execute(
        self, *, job_id, item_id, table, row_id, old_digest, patch, action="update"
    ):
        stage = "input"
        try:
            _uuid(job_id)
            _uuid(item_id)
            if type(patch) is not dict or type(row_id) is not int or row_id <= 0:
                raise _Rejected("invalid_disposition")
            serialized = json.dumps(
                patch, ensure_ascii=True, allow_nan=False, separators=(",", ":")
            )
            if len(serialized) > 65536:
                raise _Rejected("invalid_disposition")
            stage = "preparation"
            with Session(self.engine) as session, session.begin():
                connection = session.connection()
                if (
                    connection.get_isolation_level() != "READ COMMITTED"
                    or getattr(
                        connection.connection.dbapi_connection, "autocommit", None
                    )
                    is not False
                ):
                    raise _Rejected("read_committed_required")
                acquire_admin_event_locks(connection)
                if tuple(
                    connection.scalars(
                        text("SELECT version_num FROM ntubtob.alembic_version")
                    )
                ) not in (
                    ("0018_erasure_privacy_mutation",),
                    ("0019_erasure_admin_recovery",),
                    ("0020_erasure_intake",),
                    ("0021_erasure_continuity",),
                    ("0022_erasure_retention",),
                    ("0023_erasure_minimal_retention",),
                    ("0024_erasure_provider_phases",),
                ):
                    raise _Rejected("schema_not_ready")
                for name in (
                    "account_erasure_jobs",
                    "account_erasure_items",
                    "account_erasure_item_events",
                    "people",
                    "auth_identities",
                ):
                    if (
                        connection.scalar(
                            text(
                                f"SELECT pg_catalog.row_security_active('ntubtob.{name}'::regclass)"
                            )
                        )
                        is not False
                    ):
                        raise _Rejected("unfiltered_tables_required")
                job = (
                    connection.execute(
                        text(
                            "SELECT * FROM ntubtob.account_erasure_jobs WHERE id=:id FOR UPDATE"
                        ),
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
                _target(connection, job)
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
                    or item["stage"] not in {"online_erasure", "manual_redaction"}
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
                        "UPDATE ntubtob.account_erasure_jobs SET status='processing',irreversible_started_at=COALESCE(irreversible_started_at,:now),updated_at=:now WHERE id=:id"
                    ),
                    {"id": job_id, "now": now},
                )
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.account_erasure_item_events (item_id,event_sequence,event_kind,result_code,occurred_at) VALUES (:id,1,'started','in_progress',:now)"
                    ),
                    {"id": item_id, "now": now},
                )
                stage = "disposition"
                connection.execute(
                    text(
                        "SELECT ntubtob.apply_erasure_privacy_mutation(CAST(:job AS uuid),CAST(:item AS uuid),:table,:row,:old,CAST(:patch AS jsonb),:action)"
                    ),
                    dict(
                        job=job_id,
                        item=item_id,
                        table=table,
                        row=row_id,
                        old=old_digest,
                        patch=serialized,
                        action=action,
                    ),
                )
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.account_erasure_item_events (item_id,event_sequence,event_kind,result_code,occurred_at) VALUES (:id,2,'confirmed','succeeded',:now)"
                    ),
                    {"id": item_id, "now": now},
                )
                stage = "commit"
        except _Rejected as error:
            return LegacyExecutionResult("not_applied", stage, str(error))
        except Exception as error:
            if stage != "commit" and (reason := retention_failure_reason(error)):
                return LegacyExecutionResult("not_applied", stage, reason)
            # Only these literal server stages may cross the exception boundary.
            original = getattr(error, "orig", None)
            diagnostic = getattr(original, "diag", None)
            message = getattr(diagnostic, "message_primary", None)
            for check in (
                "input",
                "job_binding",
                "item_binding",
                "row_version",
                "disposition",
                "storage_mutation",
                "storage_verification",
            ):
                if message == "privacy mutation rejected at " + check:
                    return LegacyExecutionResult(
                        "not_applied", stage, "privacy_" + check + "_rejected"
                    )
            return LegacyExecutionResult(
                "outcome_unknown" if stage == "commit" else "not_applied",
                stage,
                "commit_unconfirmed" if stage == "commit" else "transaction_failed",
            )
        return LegacyExecutionResult(
            "confirmed", "commit", "item_completed", "next_item"
        )
