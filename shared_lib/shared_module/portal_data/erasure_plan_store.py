"""Default-unused same-transaction encrypted plan custody and restart handoff.

Trusted composition supplies the key registry. No keys, plaintext or ciphertext
are logged. Expiry uses the existing job evidence horizon; this is not an expiry
deletion worker, reviewer authority, provider adapter or automatic retry policy.
"""

import hmac
import re

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from ..mobile_api import utc_now
from .erasure_continuity import effective_expiry
from .erasure_fulfillment import (
    PendingIdentityFulfillment,
    PendingIdentitySnapshot,
    _identity,
)
from .erasure_person_fulfillment import PersonFulfillment, PersonSnapshot
from .erasure_plan_codec import ErasurePlanCodec
from .erasure_provider_execution import _Rejected
from .erasure_request import _instant, _uuid
from .runtime import acquire_admin_event_locks


class SealedPlanRejected(ValueError):
    """Fixed state/input rejection without plan or key representations."""


class SealedPlanUnavailable(RuntimeError):
    """Fixed storage/key failure; never permission to recapture or retry effects."""


def _reject(reason):
    raise SealedPlanRejected(reason) from None


class ErasurePlanStore:
    def __init__(self, *, active_key_id, codecs, clock=utc_now):
        if (
            type(codecs) is not dict
            or not codecs
            or not callable(clock)
            or type(active_key_id) is not str
            or active_key_id not in codecs
            or any(
                type(k) is not str
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", k) is None
                or type(v) is not ErasurePlanCodec
                for k, v in codecs.items()
            )
        ):
            raise ValueError("invalid_plan_store_configuration")
        self._active_key_id, self._codecs, self._clock = (
            active_key_id,
            dict(codecs),
            clock,
        )

    def _locked(self, connection, job_id):
        job_id = _uuid(job_id)
        if not isinstance(connection, Connection) or not connection.in_transaction():
            _reject("active_transaction_required")
        if (
            connection.get_isolation_level() != "READ COMMITTED"
            or getattr(connection.connection.dbapi_connection, "autocommit", None)
            is not False
        ):
            _reject("read_committed_required")
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
        ):
            _reject("schema_not_ready")
        for name in (
            "account_erasure_jobs",
            "account_erasure_sealed_plans",
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
                _reject("unfiltered_tables_required")
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
        if job is None:
            _reject("sealed_plan_missing")
        if job["status"] not in {
            "requested",
            "verified",
            "processing",
            "needs_attention",
        }:
            _reject("receipt_read_required")
        self._time(job, connection=connection)
        return job

    def _time(self, job, *, earliest=None, connection):
        now = _instant(self._clock())
        if not _instant(job["requested_at"]) <= now < effective_expiry(
            connection, job, "evidence_expires_at"
        ) or (earliest is not None and now < earliest):
            _reject("sealed_plan_expired")
        return now

    @staticmethod
    def _binding(connection, job, snapshot):
        if (
            job["scope_version"] != 1
            or str(job["expected_generation"]) != snapshot.generation
            or not hmac.compare_digest(job["scope_hash"], snapshot.scope_hash)
        ):
            _reject("sealed_plan_binding_changed")
        if type(snapshot) is PersonSnapshot and job["target_kind"] == "person":
            if (
                job["person_id"] != snapshot.person_id
                or job["auth_identity_id"] is not None
            ):
                _reject("sealed_plan_binding_changed")
            actual = connection.scalar(
                text(
                    "SELECT account_generation::text FROM ntubtob.people WHERE id=:id FOR UPDATE"
                ),
                {"id": snapshot.person_id},
            )
        elif (
            type(snapshot) is PendingIdentitySnapshot
            and job["target_kind"] == "pending_identity"
        ):
            if (
                job["auth_identity_id"] != snapshot.identity_id
                or job["person_id"] is not None
            ):
                _reject("sealed_plan_binding_changed")
            try:
                identity = _identity(connection, snapshot.identity_id)
            except _Rejected:
                _reject("sealed_plan_binding_changed")
            if not hmac.compare_digest(identity["digest"], snapshot.identity_digest):
                _reject("sealed_plan_binding_changed")
            actual = identity["generation"]
        else:
            _reject("sealed_plan_binding_changed")
        if actual != snapshot.generation:
            _reject("sealed_plan_binding_changed")

    def store_requested(self, connection, job_id, snapshot):
        """Caller must commit this connection's job/plan/attempt together."""
        try:
            job = self._locked(connection, job_id)
            if job["status"] != "requested":
                _reject("requested_job_required")
            if type(snapshot) not in (PersonSnapshot, PendingIdentitySnapshot):
                _reject("sealed_plan_binding_changed")
            self._binding(connection, job, snapshot)
            started = self._time(job, connection=connection)
            blob = self._codecs[self._active_key_id].encode(snapshot, job_id=job_id)
            connection.execute(
                text(
                    "INSERT INTO ntubtob.account_erasure_sealed_plans (job_id,key_id,ciphertext) VALUES (:job,:key,:blob)"
                ),
                {"job": job_id, "key": self._active_key_id, "blob": blob},
            )
            if self.load(connection, job_id) != snapshot:
                _reject("sealed_plan_readback_changed")
            self._time(job, earliest=started, connection=connection)
        except SealedPlanRejected:
            raise
        except Exception:
            raise SealedPlanUnavailable("sealed_plan_unavailable") from None

    def load(self, connection, job_id):
        try:
            job = self._locked(connection, job_id)
            row = connection.execute(
                text(
                    "SELECT key_id,ciphertext FROM ntubtob.account_erasure_sealed_plans WHERE job_id=:job FOR UPDATE"
                ),
                {"job": job_id},
            ).first()
            if row is None:
                _reject("sealed_plan_missing")
            started = self._time(job, connection=connection)
            codec = self._codecs.get(row[0])
            if codec is None:
                _reject("sealed_plan_key_unavailable")
            snapshot = codec.decode(
                bytes(row[1]),
                job_id=job_id,
                target_kind=job["target_kind"],
                generation=str(job["expected_generation"]),
                scope_hash=job["scope_hash"],
            )
            self._binding(connection, job, snapshot)
            self._time(job, earliest=started, connection=connection)
            return snapshot
        except SealedPlanRejected:
            raise
        except Exception:
            raise SealedPlanUnavailable("sealed_plan_unavailable") from None

    def execute_stored(self, engine, *, job_id, pending_executor, person_executor):
        """No caller snapshot/fallback; executors revalidate after the read TX."""
        if (
            not isinstance(engine, Engine)
            or type(pending_executor) is not PendingIdentityFulfillment
            or type(person_executor) is not PersonFulfillment
            or pending_executor.engine is not engine
            or person_executor.engine is not engine
        ):
            raise ValueError("invalid_stored_executor_configuration")
        try:
            with Session(engine) as session, session.begin():
                connection = session.connection()
                job = self._locked(connection, job_id)
                if job["status"] == "requested":
                    _reject("verified_job_required")
                snapshot = self.load(connection, job_id)
        except SealedPlanRejected:
            raise
        except Exception:
            raise SealedPlanUnavailable("sealed_plan_unavailable") from None
        executor = (
            person_executor if type(snapshot) is PersonSnapshot else pending_executor
        )
        return executor.execute(job_id=job_id, snapshot=snapshot)
