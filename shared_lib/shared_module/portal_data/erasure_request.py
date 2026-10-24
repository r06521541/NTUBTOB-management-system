"""Default-unused linked-account intent receipts, not proof or erasure authority.

The injected plan builder is trusted local read-only code: no network, mutations
or transaction management. Its explicit metadata is not an inventory guarantee.
A lost commit acknowledgement is unavailable/uncertain, never a retry instruction.
Receipt-key rotation requires explicit reconciliation; no fallback key is tried.
"""

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..mobile_api import MobilePrincipal, utc_now
from .erasure_continuity import effective_expiry
from .runtime import acquire_admin_event_locks


class ErasureRequestRejected(ValueError):
    """Fixed input or state rejection."""


class ErasureRequestUnavailable(RuntimeError):
    """Fixed configuration/storage failure; no blind retry permission."""


@dataclass(frozen=True, repr=False)
class ErasureRequestReceipt:
    job_id: str
    receipt_secret: str
    requested_at: datetime


@dataclass(frozen=True)
class ErasureRequestPlan:
    scope_version: int
    scope_hash: str
    retention_policy_version: int
    fulfillment_due_at: datetime
    receipt_expires_at: datetime
    evidence_expires_at: datetime


@dataclass(frozen=True, repr=False)
class CapturedErasureRequestPlan:
    """Trusted same-connection capture plus explicit existing policy metadata."""

    metadata: ErasureRequestPlan
    snapshot: object


def _instant(value):
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ErasureRequestRejected("invalid_time")
    return value.astimezone(timezone.utc)


def _uuid(value):
    try:
        result = str(UUID(str(value)))
        if str(value) != result:
            raise ValueError()
        return result
    except (ValueError, TypeError, AttributeError):
        raise ErasureRequestRejected("invalid_identifier") from None


class AccountErasureRequestRepository:
    def __init__(
        self, engine, key, plan_builder, clock=utc_now, *, sealed_plan_store=None
    ):
        if (
            type(key) is not bytes
            or len(key) < 32
            or not callable(plan_builder)
            or not callable(clock)
            or (
                sealed_plan_store is not None
                and (
                    not isinstance(engine, Engine)
                    or not callable(getattr(sealed_plan_store, "store_requested", None))
                    or not callable(getattr(sealed_plan_store, "load", None))
                )
            )
        ):
            raise ErasureRequestRejected("invalid_configuration")
        self.engine, self._key, self.plan_builder, self.clock = (
            engine,
            key,
            plan_builder,
            clock,
        )
        self.sealed_plan_store = sealed_plan_store

    def _build_plan(self, connection, job_id, **values):
        if self.sealed_plan_store is None:
            return self.plan_builder(**values), None
        captured = self.plan_builder(connection=connection, job_id=job_id, **values)
        if (
            type(captured) is not CapturedErasureRequestPlan
            or type(captured.metadata) is not ErasureRequestPlan
        ):
            raise ErasureRequestRejected("captured_plan_required")
        return captured.metadata, captured.snapshot

    def _secret(self, job_id):
        return hmac.new(
            self._key,
            b"ntubtob:account-erasure:receipt:v1\x00" + UUID(job_id).bytes,
            hashlib.sha256,
        ).hexdigest()

    def request(self, principal: MobilePrincipal) -> ErasureRequestReceipt:
        if not isinstance(principal, MobilePrincipal) or any(
            type(v) is not int or v <= 0
            for v in (
                principal.person_id,
                principal.identity_id,
                principal.access_epoch,
            )
        ):
            raise ErasureRequestRejected("invalid_principal")
        session_id = _uuid(principal.session_id)
        try:
            with Session(self.engine) as session, session.begin():
                if (
                    not session.in_transaction()
                    or session.new
                    or session.dirty
                    or session.deleted
                ):
                    raise ErasureRequestUnavailable("clean_transaction_required")
                connection = session.connection()
                if (
                    getattr(connection.connection.dbapi_connection, "autocommit", None)
                    is not False
                    or connection.get_isolation_level() != "READ COMMITTED"
                ):
                    raise ErasureRequestUnavailable(
                        "read_committed_transaction_required"
                    )
                acquire_admin_event_locks(connection)
                revisions = tuple(
                    connection.scalars(
                        text("SELECT version_num FROM ntubtob.alembic_version")
                    ).all()
                )
                if revisions not in (
                    ("0015_account_generations",),
                    ("0016_erasure_cancellation",),
                    ("0017_erasure_work_items",),
                    ("0018_erasure_privacy_mutation",),
                    ("0019_erasure_admin_recovery",),
                    ("0020_erasure_intake",),
                    ("0021_erasure_continuity",),
                ):
                    raise ErasureRequestUnavailable("schema_not_ready")
                for table in (
                    "account_erasure_jobs",
                    "account_deletion_requests",
                    "auth_identities",
                    "people",
                    "mobile_sessions",
                ):
                    if (
                        connection.scalar(
                            text(
                                f"SELECT pg_catalog.row_security_active('ntubtob.{table}'::pg_catalog.regclass)"
                            )
                        )
                        is not False
                    ):
                        raise ErasureRequestUnavailable("unfiltered_tables_required")

                def row(sql, **params):
                    return connection.execute(text(sql), params).mappings().first()

                identity = row(
                    "SELECT id,person_id,status FROM ntubtob.auth_identities WHERE id=:id FOR UPDATE",
                    id=principal.identity_id,
                )
                person = row(
                    "SELECT id,portal_status,account_generation FROM ntubtob.people WHERE id=:id FOR UPDATE",
                    id=principal.person_id,
                )
                device = row(
                    "SELECT id,person_id,auth_identity_id,access_epoch,status,refresh_family_expires_at FROM ntubtob.mobile_sessions WHERE id=:id FOR UPDATE",
                    id=session_id,
                )
                now = _instant(self.clock())
                if (
                    identity is None
                    or identity["id"] != principal.identity_id
                    or identity["person_id"] != principal.person_id
                    or identity["status"] != "linked"
                    or person is None
                    or person["id"] != principal.person_id
                    or person["portal_status"] != "active"
                ):
                    raise ErasureRequestRejected("active_account_required")
                if (
                    device is None
                    or str(device["id"]) != session_id
                    or device["person_id"] != principal.person_id
                    or device["auth_identity_id"] != principal.identity_id
                    or device["access_epoch"] != principal.access_epoch
                    or device["status"] != "active"
                    or _instant(device["refresh_family_expires_at"]) <= now
                ):
                    raise ErasureRequestRejected("active_session_required")
                generation = _uuid(person["account_generation"])
                job = row(
                    "SELECT id,status,target_kind,person_id,auth_identity_id,expected_generation,receipt_secret_hash,requested_at,receipt_expires_at,evidence_expires_at FROM ntubtob.account_erasure_jobs WHERE person_id=:id FOR UPDATE",
                    id=principal.person_id,
                )
                if job is not None:
                    job_id = _uuid(job["id"])
                    secret = self._secret(job_id)
                    if (
                        job["status"] != "requested"
                        or job["target_kind"] != "person"
                        or job["person_id"] != principal.person_id
                        or job["auth_identity_id"] is not None
                        or _uuid(job["expected_generation"]) != generation
                    ):
                        raise ErasureRequestRejected("request_scope_changed")
                    if type(
                        job["receipt_secret_hash"]
                    ) is not str or not hmac.compare_digest(
                        hashlib.sha256(secret.encode("ascii")).hexdigest(),
                        job["receipt_secret_hash"],
                    ):
                        raise ErasureRequestRejected("receipt_key_mismatch")
                    if (
                        effective_expiry(
                            connection, job, "receipt_expires_at", revisions=revisions
                        )
                        <= now
                        or _instant(job["requested_at"]) > now
                    ):
                        raise ErasureRequestRejected("receipt_unavailable")
                    result = ErasureRequestReceipt(
                        job_id, secret, _instant(job["requested_at"])
                    )
                    receipt_deadline = effective_expiry(
                        connection, job, "receipt_expires_at", revisions=revisions
                    )
                    if self.sealed_plan_store is not None:
                        self.sealed_plan_store.load(connection, job_id)
                else:
                    legacy = row(
                        "SELECT id,status FROM ntubtob.account_deletion_requests WHERE person_id=:id FOR UPDATE",
                        id=principal.person_id,
                    )
                    if legacy is not None and legacy["status"] != "requested":
                        raise ErasureRequestRejected("legacy_request_unavailable")
                    job_id = _uuid(legacy["id"]) if legacy is not None else str(uuid4())
                    if legacy is not None:
                        adopted = row(
                            "SELECT id,status,target_kind,person_id,auth_identity_id,expected_generation "
                            "FROM ntubtob.account_erasure_jobs WHERE id=:id FOR UPDATE",
                            id=job_id,
                        )
                        if adopted is not None:
                            # Never recycle a receipt/proof binding for a new intent.
                            # Only an explicitly cancelled, detached same-generation
                            # legacy intent permits a fresh UUID; other collisions
                            # need reconciliation rather than a guessed replacement.
                            if (
                                revisions
                                not in (
                                    ("0016_erasure_cancellation",),
                                    ("0017_erasure_work_items",),
                                    ("0018_erasure_privacy_mutation",),
                                    ("0019_erasure_admin_recovery",),
                                    ("0020_erasure_intake",),
                                    ("0021_erasure_continuity",),
                                )
                                or _uuid(adopted["id"]) != job_id
                                or adopted["status"] != "cancelled"
                                or adopted["target_kind"] != "person"
                                or adopted["person_id"] is not None
                                or adopted["auth_identity_id"] is not None
                                or _uuid(adopted["expected_generation"]) != generation
                            ):
                                raise ErasureRequestRejected("legacy_request_conflict")
                            job_id = str(uuid4())
                    plan, snapshot = self._build_plan(
                        connection,
                        job_id,
                        person_id=principal.person_id,
                        identity_id=principal.identity_id,
                        target_generation=generation,
                        requested_at=now,
                    )
                    if (
                        type(plan) is not ErasureRequestPlan
                        or any(
                            type(v) is not int or not 0 < v <= 2147483647
                            for v in (plan.scope_version, plan.retention_policy_version)
                        )
                        or type(plan.scope_hash) is not str
                        or re.fullmatch(r"[0-9a-f]{64}", plan.scope_hash) is None
                    ):
                        raise ErasureRequestRejected("invalid_plan")
                    due, receipt, evidence = (
                        _instant(v)
                        for v in (
                            plan.fulfillment_due_at,
                            plan.receipt_expires_at,
                            plan.evidence_expires_at,
                        )
                    )
                    if due <= now or receipt <= now or evidence < max(due, receipt):
                        raise ErasureRequestRejected("invalid_plan_deadlines")
                    planned_at = _instant(self.clock())
                    if (
                        planned_at < now
                        or _instant(device["refresh_family_expires_at"]) <= planned_at
                        or min(due, receipt) <= planned_at
                    ):
                        raise ErasureRequestRejected("request_expired_during_planning")
                    secret = self._secret(job_id)
                    connection.execute(
                        text(
                            "INSERT INTO ntubtob.account_erasure_jobs (id,target_kind,person_id,expected_generation,status,scope_version,scope_hash,receipt_secret_hash,retention_policy_version,requested_at,updated_at,fulfillment_due_at,receipt_expires_at,evidence_expires_at) VALUES (:id,'person',:person_id,:generation,'requested',:scope_version,:scope_hash,:receipt_hash,:policy,:now,:now,:due,:receipt,:evidence)"
                        ),
                        dict(
                            id=job_id,
                            person_id=principal.person_id,
                            generation=generation,
                            scope_version=plan.scope_version,
                            scope_hash=plan.scope_hash,
                            receipt_hash=hashlib.sha256(
                                secret.encode("ascii")
                            ).hexdigest(),
                            policy=plan.retention_policy_version,
                            now=now,
                            due=due,
                            receipt=receipt,
                            evidence=evidence,
                        ),
                    )
                    if self.sealed_plan_store is not None:
                        self.sealed_plan_store.store_requested(
                            connection, job_id, snapshot
                        )
                    receipt_deadline = min(due, receipt)
                    result = ErasureRequestReceipt(job_id, secret, now)
                final_now = _instant(self.clock())
                if (
                    final_now < now
                    or _instant(device["refresh_family_expires_at"]) <= final_now
                    or receipt_deadline <= final_now
                ):
                    raise ErasureRequestRejected("request_expired_during_planning")
            return result
        except (ErasureRequestRejected, ErasureRequestUnavailable):
            raise
        except Exception:
            raise ErasureRequestUnavailable("request_storage_or_plan_failed") from None
