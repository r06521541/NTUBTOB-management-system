"""Default-unused transactional legacy disposition, never full erasure completion.

The item must be created by the trusted inventory coordinator. A fresh, locked
scope must match that immutable item before any DELETE. Table locks deliberately
drain even legacy writers that do not participate in the lifecycle advisory lock.
No provider I/O, names, subjects, or row identifiers are returned as evidence.
"""

import hashlib
import hmac
import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..account_erasure_scope import (
    AttendanceReference,
    ErasureScopeRejected,
    LegacyIdentityReference,
    MemberReference,
    plan_legacy_attendance_erasure,
)
from ..mobile_api import utc_now
from .erasure_provider_execution import _Rejected, _target, _time, _uuid
from .erasure_retention import retention_failure_reason
from .runtime import acquire_admin_event_locks


@dataclass(frozen=True)
class LegacyExecutionResult:
    classification: str
    stage: str
    reason: str
    next_action: str = "read_only_review"


def legacy_item_binding(job_id, generation, scope):
    """Internal inventory binding; not a public digest or mutation permission."""
    return hashlib.sha256(
        json.dumps(
            [
                "legacy_erasure_v1",
                _uuid(job_id),
                _uuid(generation),
                scope.member_ids,
                scope.line_user_ids,
                scope.reply_ids,
            ],
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def _locked_scope(connection, person_id):
    # Called only after the executor locks all four relations against DML.
    members = [
        MemberReference(*row)
        for row in connection.execute(
            text("SELECT id,person_id FROM ntubtob.members WHERE person_id=:person"),
            {"person": person_id},
        )
    ]
    member_ids = [row.id for row in members]
    user_sql = (
        "SELECT u.id,u.member_id,a.person_id FROM ntubtob.line_users u "
        "LEFT JOIN ntubtob.auth_identities a ON a.provider='line' "
        "AND a.provider_subject=u.line_user_id "
    )
    users = [
        LegacyIdentityReference(*row)
        for row in connection.execute(
            text(user_sql + "WHERE u.member_id=ANY(:members) OR a.person_id=:person"),
            {"members": member_ids, "person": person_id},
        )
    ]
    user_ids = [row.id for row in users]
    replies = [
        AttendanceReference(*row)
        for row in connection.execute(
            text(
                "SELECT id,person_id,member_id,user_id FROM ntubtob.game_attendance_replies "
                "WHERE person_id=:person OR member_id=ANY(:members) OR user_id=ANY(:users)"
            ),
            {"person": person_id, "members": member_ids, "users": user_ids},
        )
    ]
    referenced_users = {row.user_id for row in replies if row.user_id is not None}
    users.extend(
        LegacyIdentityReference(*row)
        for row in connection.execute(
            text(user_sql + "WHERE u.id=ANY(:ids)"),
            {"ids": sorted(referenced_users - set(user_ids))},
        )
    )
    referenced_members = {
        row.member_id for row in replies + users if row.member_id is not None
    }
    members.extend(
        MemberReference(*row)
        for row in connection.execute(
            text("SELECT id,person_id FROM ntubtob.members WHERE id=ANY(:ids)"),
            {"ids": sorted(referenced_members - set(member_ids))},
        )
    )
    return plan_legacy_attendance_erasure(person_id, members, users, replies)


class LegacyErasureExecutor:
    """One atomic local transaction: fence, exact deletes, and item evidence.

    A successful result means this item only. Person, identities, shared content,
    credentials, other stores and restore suppression remain separate work.
    A commit disconnect is unknown, not permission to invoke execute again.
    """

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
                    ("0017_erasure_work_items",),
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
                    "people",
                    "auth_identities",
                    "members",
                    "line_users",
                    "game_attendance_replies",
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
                if (
                    job is None
                    or job["status"]
                    not in {"verified", "processing", "needs_attention"}
                    or job["target_kind"] != "person"
                ):
                    raise _Rejected("verified_person_job_required")
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
                connection.execute(
                    text(
                        "LOCK TABLE ntubtob.auth_identities,ntubtob.members,ntubtob.line_users,ntubtob.game_attendance_replies IN SHARE ROW EXCLUSIVE MODE"
                    )
                )
                scope = _locked_scope(connection, job["person_id"])
                if not (scope.member_ids or scope.line_user_ids or scope.reply_ids):
                    raise _Rejected("empty_scope")
                if not hmac.compare_digest(
                    legacy_item_binding(job_id, str(job["expected_generation"]), scope),
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
                for table, ids in (
                    ("game_attendance_replies", scope.reply_ids),
                    ("line_users", scope.line_user_ids),
                    ("members", scope.member_ids),
                ):
                    result = connection.execute(
                        text(f"DELETE FROM ntubtob.{table} WHERE id=ANY(:ids)"),
                        {"ids": list(ids)},
                    )
                    if result.rowcount != len(ids):
                        raise _Rejected("disposition_count_changed")
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.account_erasure_item_events (item_id,event_sequence,event_kind,result_code,occurred_at) VALUES (:id,2,'confirmed','succeeded',:now)"
                    ),
                    {"id": item_id, "now": now},
                )
                stage = "commit"
        except ErasureScopeRejected:
            return LegacyExecutionResult("not_applied", stage, "ownership_conflict")
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
